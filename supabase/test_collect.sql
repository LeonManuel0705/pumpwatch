\set ON_ERROR_STOP on
\pset pager off

truncate price_changes, station_state, stations, poll_log restart identity cascade;
truncate pending_request, net._http_response;
truncate net.sent_requests restart identity;
delete from vault.decrypted_secrets;

select collect_prices(p_offset_seconds => 0);
select assert_eq((select count(*)::integer from net.sent_requests), 0, 'no request goes out without an API key');
select assert_eq((select error from poll_log order by id desc limit 1),
    'tankerkoenig_api_key missing from vault', 'the missing key is logged');

insert into vault.decrypted_secrets (name, decrypted_secret) values ('tankerkoenig_api_key', 'test-key-123');

select collect_prices(p_offset_seconds => 0);
select assert_eq((select count(*)::integer from net.sent_requests), 1, 'the first run sends one request');
select assert_eq((select url like '%lat=52.3785&lng=12.9337&rad=25&%&apikey=test-key-123'
                  from net.sent_requests where id = 1), true, 'the request covers the region and carries the key');
select assert_eq((select headers ->> 'User-Agent' from net.sent_requests where id = 1),
    'pumpwatch/1.0 (research project; non-commercial)', 'the request identifies itself');
select assert_eq((select request_id from pending_request), 1::bigint, 'the request is remembered');

select collect_prices(p_offset_seconds => 0);
select assert_eq((select count(*)::integer from net.sent_requests), 1,
    'a second run inside the spacing window sends nothing');
select assert_eq((select error like 'skipped: previous request only %' from poll_log order by id desc limit 1),
    true, 'the skipped run is logged');
select assert_eq((select request_id from pending_request), 1::bigint, 'the skipped run leaves the pending request alone');

select date_trunc('second', now() - interval '4 minutes 58 seconds') as response_time \gset
update pending_request set sent_at = now() - interval '5 minutes';
insert into net._http_response (id, status_code, content, created) values (1, 200,
    '{"ok":true,"stations":[
        {"id":"11111111-1111-1111-1111-111111111111","name":"Star Werder","brand":"STAR",
         "street":"Chaussee","houseNumber":"1","postCode":14542,"place":"Werder",
         "lat":52.3785,"lng":12.9337,"isOpen":true,"e5":2.189,"e10":2.129,"diesel":2.229},
        {"id":"22222222-2222-2222-2222-222222222222","name":"Aral","brand":"ARAL",
         "street":"Zeppelin","houseNumber":"10","postCode":14471,"place":"Potsdam",
         "lat":52.39,"lng":13.06,"isOpen":true,"e5":2.199,"e10":false,"diesel":2.239}
    ]}', :'response_time');

select collect_prices(p_offset_seconds => 0);
select assert_eq((select count(*)::integer from price_changes), 2, 'the previous response is ingested');
select assert_eq((select count(*)::integer from price_changes where observed_at = :'response_time'),
    2, 'prices are dated to the response, not to the next run');
select assert_eq((select count(*)::integer from net._http_response where id = 1), 0, 'the ingested response is removed');
select assert_eq((select count(*)::integer from net.sent_requests), 2, 'the next request goes out after ingesting');
select assert_eq((select request_id from pending_request), 2::bigint, 'the new request replaces the old one');

update pending_request set sent_at = now() - interval '5 minutes';
insert into net._http_response (id, status_code, content) values (2, 200, '<html>Wartungsarbeiten</html>');
select collect_prices(p_offset_seconds => 0);
select assert_eq((select error like 'ingest failed: %' from poll_log order by id desc limit 1),
    true, 'a non JSON body is logged');
select assert_eq((select count(*)::integer from net.sent_requests), 3, 'a broken response does not stall the collector');
select assert_eq((select count(*)::integer from net._http_response where id = 2), 0, 'the broken response is removed');

update pending_request set sent_at = now() - interval '5 minutes';
insert into net._http_response (id, status_code, content) values (3, 503, 'busy');
select collect_prices(p_offset_seconds => 0);
select assert_eq((select error from poll_log order by id desc limit 1), 'HTTP 503', 'an HTTP error is logged');
select assert_eq((select count(*)::integer from net.sent_requests), 4, 'collection continues after an HTTP error');

update pending_request set sent_at = now() - interval '5 minutes';
insert into net._http_response (id, timed_out, error_msg) values (4, true, 'Timeout of 25000 ms reached');
select collect_prices(p_offset_seconds => 0);
select assert_eq((select error from poll_log order by id desc limit 1),
    'Timeout of 25000 ms reached', 'a transport error keeps its message');

select date_trunc('second', now() - interval '5 minutes') as sent_time \gset
update pending_request set sent_at = :'sent_time';
select collect_prices(p_offset_seconds => 0);
select assert_eq((select error from poll_log order by id desc limit 1), 'no response arrived', 'a lost response is logged');
select assert_eq((select started_at from poll_log order by id desc limit 1), :'sent_time'::timestamptz,
    'a failed poll is dated to its request');
select assert_eq((select count(*)::integer from net.sent_requests), 6, 'collection continues after a lost response');

select assert_eq((select stations from collector_health), 2::bigint, 'health counts the stations');
select assert_eq((select last_success from collector_health), :'response_time'::timestamptz,
    'health reports the last good poll');

select assert_eq(has_function_privilege('anon',
    'public.collect_prices(text, numeric, numeric, numeric, integer, interval)', 'execute'),
    false, 'anon cannot fire requests with the API key');
select assert_eq(has_function_privilege('authenticated',
    'public.collect_prices(text, numeric, numeric, numeric, integer, interval)', 'execute'),
    false, 'signed in users cannot fire requests either');
select assert_eq(has_function_privilege('anon', 'public.ingest_stations(jsonb, text, timestamptz)', 'execute'),
    false, 'anon cannot inject prices');
select assert_eq(has_function_privilege('anon', 'public.prune_http_responses(interval)', 'execute'),
    false, 'anon cannot prune');
select assert_eq(has_table_privilege('anon', 'public.collector_health', 'select'),
    true, 'anon can read the health view for the watchdog');

select 'all collector checks passed' as result;

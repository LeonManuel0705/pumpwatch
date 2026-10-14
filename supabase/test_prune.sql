\set ON_ERROR_STOP on
\pset pager off

truncate net._http_response;
truncate pending_request;

insert into net._http_response (id, status_code, content, created) values
    (1, 200, '{}', now() - interval '3 hours'),
    (2, 200, '{}', now() - interval '45 minutes'),
    (3, 200, '{}', now() - interval '11 minutes'),
    (4, 200, '{}', now() - interval '4 minutes'),
    (5, 200, '{}', now());

insert into pending_request (id, request_id, region) values (true, 2, 'test');

select assert_eq(public.prune_http_responses(), 2, 'deletes only responses older than ten minutes');
select assert_eq((select count(*)::integer from net._http_response where id = 2), 1,
    'the response still waiting to be ingested survives');
select assert_eq((select count(*)::integer from net._http_response), 3, 'recent responses survive');

update pending_request set request_id = null;
select assert_eq(public.prune_http_responses('0 minutes'), 3, 'an explicit interval is honoured');
select assert_eq(public.prune_http_responses(), 0, 'pruning an empty table is a no-op');

drop table net._http_response;
truncate public.poll_log restart identity;
select assert_eq(public.prune_http_responses(), 0, 'a missing pg_net table does not raise');
select assert_eq((select count(*)::integer from public.poll_log where region = 'prune' and not ok),
    1, 'the failure is recorded instead of killing the cron job');

select 'all prune checks passed' as result;

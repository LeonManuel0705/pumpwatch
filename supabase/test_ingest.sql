\set ON_ERROR_STOP on
\pset pager off

create or replace function assert_eq(actual anyelement, expected anyelement, label text)
returns void language plpgsql as $$
begin
    if actual is distinct from expected then
        raise exception 'FAIL % : expected %, got %', label, expected, actual;
    end if;
    raise notice '  ok  % (%)', label, actual;
end;
$$;

truncate price_changes, station_state, stations, poll_log restart identity cascade;

select assert_eq(
    ingest_stations('{"ok":true,"stations":[
        {"id":"11111111-1111-1111-1111-111111111111","name":"Star Werder","brand":"STAR",
         "street":"Chaussee","houseNumber":"1","postCode":14542,"place":"Werder",
         "lat":52.3785,"lng":12.9337,"isOpen":true,"e5":2.189,"e10":2.129,"diesel":2.229},
        {"id":"22222222-2222-2222-2222-222222222222","name":"Aral","brand":"ARAL",
         "street":"Zeppelin","houseNumber":"10","postCode":14471,"place":"Potsdam",
         "lat":52.39,"lng":13.06,"isOpen":true,"e5":2.199,"e10":false,"diesel":2.239}
    ]}'::jsonb, 'test'),
    2, 'first poll records both stations');

select assert_eq((select e10 from station_state where station_id = '22222222-2222-2222-2222-222222222222'),
    null::integer, 'e10 false becomes NULL');
select assert_eq((select e5 from station_state where station_id = '11111111-1111-1111-1111-111111111111'),
    2189, 'euro float becomes tenths of a cent');

select pg_sleep(0.01);
select assert_eq(
    ingest_stations('{"ok":true,"stations":[
        {"id":"11111111-1111-1111-1111-111111111111","name":"Star Werder","brand":"STAR",
         "street":"Chaussee","houseNumber":"1","postCode":14542,"place":"Werder",
         "lat":52.3785,"lng":12.9337,"isOpen":true,"e5":2.189,"e10":2.129,"diesel":2.229},
        {"id":"22222222-2222-2222-2222-222222222222","name":"Aral","brand":"ARAL",
         "street":"Zeppelin","houseNumber":"10","postCode":14471,"place":"Potsdam",
         "lat":52.39,"lng":13.06,"isOpen":true,"e5":2.199,"e10":false,"diesel":2.239}
    ]}'::jsonb, 'test'),
    0, 'identical poll records nothing');

select pg_sleep(0.01);
select assert_eq(
    ingest_stations('{"ok":true,"stations":[
        {"id":"11111111-1111-1111-1111-111111111111","name":"Star Werder","brand":"STAR",
         "street":"Chaussee","houseNumber":"1","postCode":14542,"place":"Werder",
         "lat":52.3785,"lng":12.9337,"isOpen":true,"e5":2.149,"e10":2.089,"diesel":2.229},
        {"id":"22222222-2222-2222-2222-222222222222","name":"Aral","brand":"ARAL",
         "street":"Zeppelin","houseNumber":"10","postCode":14471,"place":"Potsdam",
         "lat":52.39,"lng":13.06,"isOpen":true,"e5":2.199,"e10":false,"diesel":2.239}
    ]}'::jsonb, 'test'),
    1, 'only the station that moved is recorded');

select pg_sleep(0.01);
select assert_eq(
    ingest_stations('{"ok":true,"stations":[
        {"id":"11111111-1111-1111-1111-111111111111","name":"Star Werder","brand":"STAR",
         "street":"Chaussee","houseNumber":"1","postCode":14542,"place":"Werder",
         "lat":52.3785,"lng":12.9337,"isOpen":false}
    ]}'::jsonb, 'test'),
    1, 'closing is itself a change');

select assert_eq((select e5 from station_state where station_id = '11111111-1111-1111-1111-111111111111'),
    2149, 'closed station keeps its last price');

select assert_eq((select count(*)::integer from price_changes
                  where station_id = '11111111-1111-1111-1111-111111111111'),
    3, 'star has three recorded states');

select assert_eq(ingest_stations('{"ok":false}'::jsonb, 'test'), 0, 'malformed payload is survived');
select assert_eq((select count(*)::integer from poll_log where ok = false), 1, 'failure is logged');

select '', 'all ingest checks passed' as result;

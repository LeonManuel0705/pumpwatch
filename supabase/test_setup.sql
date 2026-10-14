\set ON_ERROR_STOP on

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
end;
$$;

alter default privileges in schema public grant all on tables to anon, authenticated;
alter default privileges in schema public grant all on sequences to anon, authenticated;
alter default privileges in schema public grant all on functions to anon, authenticated;

create schema if not exists net;

create table if not exists net._http_response (
    id          bigint primary key,
    status_code integer,
    content     text,
    timed_out   boolean,
    error_msg   text,
    created     timestamptz not null default now()
);

create table if not exists net.sent_requests (
    id      bigserial primary key,
    url     text not null,
    headers jsonb not null,
    timeout integer not null
);

create or replace function net.http_get(
    url text,
    params jsonb default '{}',
    headers jsonb default '{}',
    timeout_milliseconds integer default 5000
) returns bigint language sql as $$
    insert into net.sent_requests (url, headers, timeout)
    values (url, headers, timeout_milliseconds)
    returning id;
$$;

create schema if not exists vault;

create table if not exists vault.decrypted_secrets (
    name             text primary key,
    decrypted_secret text not null
);

create or replace function assert_eq(actual anyelement, expected anyelement, label text)
returns void language plpgsql as $$
begin
    if actual is distinct from expected then
        raise exception 'FAIL % : expected %, got %', label, expected, actual;
    end if;
    raise notice '  ok  % (%)', label, actual;
end;
$$;

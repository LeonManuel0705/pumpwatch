create extension if not exists pg_net;
create extension if not exists pg_cron;

create or replace function public.collect_prices(
    p_region text default 'werder-potsdam',
    p_lat numeric default 52.3785,
    p_lng numeric default 12.9337,
    p_radius numeric default 25
) returns void language plpgsql security definer set search_path = public, net, vault as $$
declare
    v_pending    bigint;
    v_region     text;
    v_status     integer;
    v_content    text;
    v_api_key    text;
    v_url        text;
    v_request_id bigint;
begin
    select request_id, region into v_pending, v_region from pending_request where id;

    if v_pending is not null then
        select status_code, content into v_status, v_content
        from net._http_response where id = v_pending;

        if v_status is null then
            insert into poll_log (region, ok, error) values (v_region, false, 'no response yet');
        elsif v_status <> 200 then
            insert into poll_log (region, ok, error)
            values (v_region, false, format('HTTP %s', v_status));
        else
            perform ingest_stations(v_content::jsonb, v_region);
        end if;

        delete from net._http_response where id = v_pending;
    end if;

    select decrypted_secret into v_api_key
    from vault.decrypted_secrets where name = 'tankerkoenig_api_key';

    if v_api_key is null then
        insert into poll_log (region, ok, error)
        values (p_region, false, 'tankerkoenig_api_key missing from vault');
        return;
    end if;

    v_url := format(
        'https://creativecommons.tankerkoenig.de/json/list.php?lat=%s&lng=%s&rad=%s&sort=dist&type=all&apikey=%s',
        p_lat, p_lng, p_radius, v_api_key);

    select net.http_get(url := v_url, timeout_milliseconds := 25000) into v_request_id;

    insert into pending_request (id, request_id, region, sent_at)
    values (true, v_request_id, p_region, now())
    on conflict (id) do update set
        request_id = excluded.request_id,
        region = excluded.region,
        sent_at = excluded.sent_at;
end;
$$;

create or replace function public.prune_http_responses(p_keep interval default '10 minutes')
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_deleted integer := 0;
begin
    delete from net._http_response where created < now() - p_keep;
    get diagnostics v_deleted = row_count;
    return v_deleted;
exception
    when insufficient_privilege or undefined_table then
        insert into public.poll_log (region, ok, error)
        values ('prune', false, 'cannot delete from net._http_response: ' || sqlerrm);
        return 0;
end;
$$;

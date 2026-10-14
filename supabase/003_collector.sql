drop function if exists public.collect_prices(text, numeric, numeric, numeric);

create or replace function public.collect_prices(
    p_region text default 'werder-potsdam',
    p_lat numeric default 52.3785,
    p_lng numeric default 12.9337,
    p_radius numeric default 25,
    p_offset_seconds integer default 23,
    p_min_spacing interval default '4 minutes'
) returns void language plpgsql security definer set search_path = public, net, vault as $$
declare
    v_pending    bigint;
    v_region     text;
    v_sent_at    timestamptz;
    v_response   record;
    v_api_key    text;
    v_url        text;
    v_request_id bigint;
begin
    select request_id, region, sent_at into v_pending, v_region, v_sent_at
    from pending_request where id for update;

    if v_sent_at > now() - p_min_spacing then
        insert into poll_log (region, ok, error)
        values (p_region, false,
                format('skipped: previous request only %s ago', date_trunc('second', now() - v_sent_at)));
        return;
    end if;

    if v_pending is not null then
        select status_code, content, timed_out, error_msg, created into v_response
        from net._http_response where id = v_pending;

        if not found then
            insert into poll_log (region, started_at, ok, error)
            values (v_region, v_sent_at, false, 'no response arrived');
        elsif v_response.error_msg is not null or v_response.timed_out then
            insert into poll_log (region, started_at, ok, error)
            values (v_region, v_sent_at, false, coalesce(v_response.error_msg, 'request timed out'));
        elsif v_response.status_code <> 200 then
            insert into poll_log (region, started_at, ok, error)
            values (v_region, v_sent_at, false, format('HTTP %s', v_response.status_code));
        else
            begin
                perform ingest_stations(v_response.content::jsonb, v_region, v_response.created);
            exception when others then
                insert into poll_log (region, started_at, ok, error)
                values (v_region, v_response.created, false, 'ingest failed: ' || sqlerrm);
            end;
        end if;

        delete from net._http_response where id = v_pending;
        update pending_request set request_id = null where id;
    end if;

    select decrypted_secret into v_api_key
    from vault.decrypted_secrets where name = 'tankerkoenig_api_key';

    if v_api_key is null then
        insert into poll_log (region, ok, error)
        values (p_region, false, 'tankerkoenig_api_key missing from vault');
        return;
    end if;

    -- Tankerkoenig asks automated clients to stay off round times
    if p_offset_seconds > 0 then
        perform pg_sleep(p_offset_seconds);
    end if;

    v_url := format(
        'https://creativecommons.tankerkoenig.de/json/list.php?lat=%s&lng=%s&rad=%s&sort=dist&type=all&apikey=%s',
        p_lat, p_lng, p_radius, v_api_key);

    select net.http_get(
        url := v_url,
        headers := jsonb_build_object('User-Agent', 'pumpwatch/1.0 (research project; non-commercial)'),
        timeout_milliseconds := 25000
    ) into v_request_id;

    insert into pending_request (id, request_id, region, sent_at)
    values (true, v_request_id, p_region, clock_timestamp())
    on conflict (id) do update set
        request_id = excluded.request_id,
        region = excluded.region,
        sent_at = excluded.sent_at;
end;
$$;

revoke execute on function public.collect_prices(text, numeric, numeric, numeric, integer, interval)
    from public, anon, authenticated;

create or replace function public.prune_http_responses(p_keep interval default '10 minutes')
returns integer language plpgsql security definer set search_path = '' as $$
declare
    v_deleted integer := 0;
begin
    delete from net._http_response
    where created < now() - p_keep
      and id is distinct from (select request_id from public.pending_request where id);
    get diagnostics v_deleted = row_count;
    return v_deleted;
exception
    when insufficient_privilege or undefined_table then
        insert into public.poll_log (region, ok, error)
        values ('prune', false, 'cannot delete from net._http_response: ' || sqlerrm);
        return 0;
end;
$$;

revoke execute on function public.prune_http_responses(interval) from public, anon, authenticated;

create or replace function public.price_field(entry jsonb, field text)
returns integer language sql immutable as $$
    select case
        when jsonb_typeof(entry -> field) = 'number'
             and (entry ->> field)::numeric > 0
        then round((entry ->> field)::numeric * 1000)::integer
        else null
    end;
$$;

create or replace function public.ingest_stations(payload jsonb, region text default 'default')
returns integer language plpgsql security definer set search_path = public as $$
declare
    v_changes integer := 0;
    v_count   integer := 0;
    v_now     timestamptz := now();
begin
    if payload is null or jsonb_typeof(payload -> 'stations') is distinct from 'array' then
        insert into poll_log (region, started_at, ok, error)
        values (region, v_now, false, 'payload had no stations array');
        return 0;
    end if;

    create temporary table incoming on commit drop as
    select
        (entry ->> 'id')::uuid                        as station_id,
        coalesce(entry ->> 'name', '')                as name,
        coalesce(entry ->> 'brand', '')               as brand,
        coalesce(entry ->> 'street', '')              as street,
        coalesce(entry ->> 'houseNumber', '')         as house_number,
        coalesce(entry ->> 'postCode', '')            as post_code,
        coalesce(entry ->> 'place', '')               as place,
        (entry ->> 'lat')::double precision           as lat,
        (entry ->> 'lng')::double precision           as lng,
        coalesce((entry ->> 'isOpen')::boolean, false) as is_open,
        price_field(entry, 'e5')                      as e5,
        price_field(entry, 'e10')                     as e10,
        price_field(entry, 'diesel')                  as diesel
    from jsonb_array_elements(payload -> 'stations') as entry
    where entry ? 'id' and (entry ->> 'id') <> '';

    select count(*) into v_count from incoming;

    insert into stations (station_id, name, brand, street, house_number,
                          post_code, place, lat, lng, first_seen, last_seen)
    select station_id, name, brand, street, house_number,
           post_code, place, lat, lng, v_now, v_now
    from incoming
    on conflict (station_id) do update set
        name = excluded.name, brand = excluded.brand, street = excluded.street,
        house_number = excluded.house_number, post_code = excluded.post_code,
        place = excluded.place, lat = excluded.lat, lng = excluded.lng,
        last_seen = excluded.last_seen;

    create temporary table merged on commit drop as
    select
        i.station_id,
        coalesce(i.e5,     s.e5)     as e5,
        coalesce(i.e10,    s.e10)    as e10,
        coalesce(i.diesel, s.diesel) as diesel,
        i.is_open
    from incoming i
    left join station_state s using (station_id);

    with changed as (
        select m.*
        from merged m
        left join station_state s using (station_id)
        where s.station_id is null
           or m.e5      is distinct from s.e5
           or m.e10     is distinct from s.e10
           or m.diesel  is distinct from s.diesel
           or m.is_open is distinct from s.is_open
    ), inserted as (
        insert into price_changes (station_id, observed_at, e5, e10, diesel, is_open)
        select station_id, v_now, e5, e10, diesel, is_open from changed
        on conflict (station_id, observed_at) do nothing
        returning 1
    )
    select count(*) into v_changes from inserted;

    insert into station_state (station_id, e5, e10, diesel, is_open, updated_at)
    select station_id, e5, e10, diesel, is_open, v_now from merged
    on conflict (station_id) do update set
        e5 = excluded.e5, e10 = excluded.e10, diesel = excluded.diesel,
        is_open = excluded.is_open, updated_at = excluded.updated_at;

    insert into poll_log (region, started_at, station_count, change_count, ok)
    values (region, v_now, v_count, v_changes, true);

    return v_changes;
end;
$$;

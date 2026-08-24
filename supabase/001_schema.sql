create table if not exists public.stations (
    station_id   uuid primary key,
    name         text not null default '',
    brand        text not null default '',
    street       text not null default '',
    house_number text not null default '',
    post_code    text not null default '',
    place        text not null default '',
    lat          double precision,
    lng          double precision,
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now()
);

create table if not exists public.station_state (
    station_id uuid primary key references public.stations (station_id) on delete cascade,
    e5         integer,
    e10        integer,
    diesel     integer,
    is_open    boolean not null,
    updated_at timestamptz not null default now()
);

create table if not exists public.price_changes (
    station_id  uuid not null references public.stations (station_id) on delete cascade,
    observed_at timestamptz not null,
    e5          integer,
    e10         integer,
    diesel      integer,
    is_open     boolean not null,
    primary key (station_id, observed_at)
);

create index if not exists idx_price_changes_time on public.price_changes (observed_at);
create index if not exists idx_price_changes_station_time on public.price_changes (station_id, observed_at desc);

create table if not exists public.poll_log (
    id            bigserial primary key,
    region        text not null,
    started_at    timestamptz not null default now(),
    station_count integer not null default 0,
    change_count  integer not null default 0,
    ok            boolean not null,
    error         text
);

create index if not exists idx_poll_log_time on public.poll_log (started_at desc);

create table if not exists public.pending_request (
    id         boolean primary key default true check (id),
    request_id bigint not null,
    region     text not null,
    sent_at    timestamptz not null default now()
);

alter table public.stations      enable row level security;
alter table public.station_state enable row level security;
alter table public.price_changes enable row level security;
alter table public.poll_log      enable row level security;
alter table public.pending_request enable row level security;

drop policy if exists "public read stations" on public.stations;
create policy "public read stations" on public.stations for select using (true);

drop policy if exists "public read prices" on public.price_changes;
create policy "public read prices" on public.price_changes for select using (true);

drop policy if exists "public read state" on public.station_state;
create policy "public read state" on public.station_state for select using (true);

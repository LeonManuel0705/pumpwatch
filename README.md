# pumpwatch

An empirical study of how German fuel retailers actually set their prices, built on a
dataset I collect myself at minute resolution for every filling station within 25 km of
Werder (Havel).

Fuel prices in Germany move several times a day in a pattern that looks coordinated
without anyone being allowed to coordinate. The question is whether that pattern survives
contact with data: who moves first, how fast the others follow, and whether any of it is
worth anything to a driver deciding when to fill up.

## Research questions

1. **Price cycles.** How many times a day does a station change its price, and how regular
   are the daily peaks and troughs? This is the empirical shape of an Edgeworth cycle.
2. **Price leadership.** When a price falls, which brand moves first, and how many minutes
   pass before competitors follow? The ordering plus the lag is the observable signature of
   tacit coordination.
3. **Competition and price level.** Does a station's price depend on how many rivals sit
   within 1, 3 and 5 km of it?
4. **The payoff.** What does an optimal refuelling time save a normal driver over a year,
   and how much of that survives once the detour is priced in?

## Why the data is collected rather than downloaded

Tankerkönig publishes a historical archive of every MTS-K price change since 2014, but the
repository behind it now requires a verified account. The live API, by contrast, is open
with a free key, and a single request returns every station inside a 25 km radius. Polling
that endpoint every five minutes yields nearly the same substance for the chosen region,
and the resulting dataset is genuinely first hand. Both paths are implemented, so the
archive can be folded in if access ever comes through.

## Design decisions that matter

**Five minutes, not one.** The API technically accepts one request a minute, but its terms
ask automated clients for at most one every five minutes, at times that are not round, and
they deactivate keys that load the service harder. A deactivated key cannot simply be
replaced, so the collector polls every five minutes at a fixed odd offset (minute 3, 8, 13
and so on, second 23). The cost is resolution: a station that changes its price twice
inside one window shows only the second price, and leader and follower lags in question
two are measured in five minute steps.

**Store changes, not snapshots.** Writing all 80 stations every five minutes would produce
about 23,000 rows a day. Writing a row only when a price or the open state actually changes
brings that down to a few hundred, which is the same compression the MTS-K applies
internally, with no loss of information.

**Prices as integer tenths of a cent.** A price of 1.719 euro is stored as `1719`. Change
detection is then exact equality rather than a float comparison with a tolerance that
would either miss real changes or invent them.

**Log every poll, including the failures.** `poll_log` records duration, station count and
any error for every single request. Downtime that is not recorded does not vanish from the
analysis, it silently becomes an absence of price changes, and any study that ignores it
will understate volatility. Making gaps auditable is the difference between a dataset and
a pile of rows.

**No third party dependencies in the collector.** It uses only the Python standard library,
because it is meant to run unattended for a year on an always on machine and a dependency
that breaks in month seven costs more than the convenience was ever worth.

**Two gotchas in the historical archive**, both of which corrupt the analysis silently:

* Timestamps carry an offset, `+01` in winter and `+02` in summer. Read as UTC, every
  summer observation shifts an hour earlier and smears the daily cycle exactly where the
  cycle is the object of study. Every row therefore also stores `local_time`, `local_hour`,
  `local_minute` and `local_dow` in `Europe/Berlin`.
* A price of `0.000` means the station does not sell that fuel, not that it is free. On the
  test fixture, treating those as zero drags the mean E10 price from 161.4 cents down to
  129.1.

## Data model

| Table | Contents |
|:---|:---|
| `stations` | Master data per station, plus the first and last time it was seen |
| `price_changes` | One row only when a price or the open state changes |
| `poll_log` | Every request, with duration, station count and any error |

A closed station reports no prices at all, so its last known prices are carried forward
rather than written as nulls, which would otherwise read as a price collapse every night.

## Setup

```bash
export TANKERKOENIG_API_KEY=<free key from https://onboarding.tankerkoenig.de>
python3 scripts/run_collector.py
```

Optional: `PUMPWATCH_DB` for the database path, `PUMPWATCH_INTERVAL` for the polling
interval in seconds (floored at 300, see above). Copy `regions.json.example` to
`regions.json` to rotate across several regions.

```bash
python3 scripts/test_collector.py             # collector tests, no network needed
python3 scripts/test_dump_import.py           # importer tests, no archive needed
python3 scripts/stats.py                      # rows collected, coverage, top brands
```

## Running it in Supabase

This is the production setup. The collector lives in Postgres rather than on a machine
that has to stay awake, and a front end can read the data directly: a SQLite file behind
a home router is unreachable, a Supabase table is not.

1. Create a free Supabase project in the Frankfurt region.
2. Add three lines to `.env` next to the Tankerkönig key: `SUPABASE_DB_URL` (the session
   pooler connection string from the project's Connect dialog, which works over IPv4),
   `SUPABASE_URL` and `SUPABASE_ANON_KEY` (the publishable key).
3. Run `scripts/supabase_setup.sh`. It applies the files below in order and stores the API
   key in Supabase Vault, read from the environment so it never appears in a file or a
   command line. Running it again is safe.
4. Run `scripts/install_watchdog.sh` on a Mac that is used daily.

| file | contents |
|---|---|
| `supabase/000_extensions.sql` | enables pg_net and pg_cron |
| `supabase/001_schema.sql` | tables, indexes, row level security |
| `supabase/002_ingest.sql` | JSON parsing, change detection, the health view |
| `supabase/003_collector.sql` | pg_net request cycle, response pruning |
| `supabase/004_schedule.sql` | the API key and the two cron jobs |

`pg_cron` fires `collect_prices()` every five minutes. Because `pg_net` is asynchronous,
each run first ingests the response to the *previous* request and then issues the next
one. Every row is dated to the moment that response arrived, not to the run that
processed it, so the five minute delay never reaches the data. The run is built so that
no single bad reply can stop it: an HTML error page, an HTTP error, a timeout or a lost
response each become a row in `poll_log`, and the next request goes out regardless. A
spacing guard refuses to send a second request within four minutes of the last, so a
manual run or a duplicated cron job cannot push the key over the limit.

**Nothing outside the database can trigger a request.** Postgres lets every role call
every function by default, and Supabase hands its publishable key to anyone who loads a
front end. Without an explicit revoke, that key could call `collect_prices()` in a loop
until Tankerkönig blocks the API key, or call `ingest_stations()` with invented prices.
Both are revoked from `anon` and `authenticated`; the public can read stations, prices and
the health view, nothing else.

**Free projects pause after a week without user activity**, and whether pg_cron's own
traffic counts is not documented. A paused project stops collecting silently. The
watchdog closes that gap: twice a day it reads `collector_health` through the REST API,
which is real user traffic, and posts a macOS notification if the last successful poll
is more than 30 minutes old. Its log is in `~/Library/Logs/pumpwatch-watchdog.log`.

Two things keep this inside the free tier:

- **`net._http_response` is kept small.** pg_net stores every reply and expires it after
  its own six hour TTL. That TTL has been reported to miss rows, and `alter system set
  pg_net.ttl` needs superuser rights that a hosted project does not grant, so
  `prune_http_responses()` runs every ten minutes as a backstop. It never deletes the
  response that is still waiting to be ingested, and if the table is unreachable it
  records that in `poll_log` rather than raising, so one permission problem cannot leave
  the cron job failing silently forever.
- **Only changes are stored.** A few hundred changed rows a day plus 288 poll log rows
  works out well under 100 MB a year, against a 500 MB database limit.

`scripts/test_supabase.sh` starts a throwaway local Postgres, stubs pg_net and Vault, and
runs the ingest, collector and pruning checks against it, including the privilege
lockdown. Once the job is live, `select * from collector_health` shows the last success,
polls in the past hour, recent failures and the table size in one row.

**Only one collector may run at a time.** Running the Python daemon and the Supabase job
together doubles the request rate against one key.

## Running it permanently

The collector belongs on a machine that stays on, not a laptop that sleeps. Clone it there,
set the key in the environment, and register it as a service so it comes back after a
reboot. Because gaps are logged rather than hidden, an imperfect uptime is a known quantity
in the analysis instead of a silent bias.

## Importing the historical archive

The MTS-K archive ships one CSV per day, each row a single price change at second
resolution. The importer converts it to partitioned Parquet, which is what makes a decade
of national price changes queryable on a laptop:

```bash
python3 scripts/import_dump.py --source ~/tankerkoenig-data --out data/parquet
```

It is incremental, skips months that are already converted, and stops before it fills the
disk. Output uses the same integer tenths of a cent as the collector, so both sources can
be queried in one statement.

## Status

The collector, the Supabase job and the importer are written and tested. Continuous
collection starts with the Supabase project; the analysis in question one onward needs
several weeks of accumulated data before it says anything, which is the nature of the
object being studied.

## Attribution

Price data originates from the Markttransparenzstelle für Kraftstoffe (MTS-K) and is
provided by Tankerkönig under CC BY 4.0. Any published chart or claim carries that
attribution.

## License

MIT for the code. The data carries the attribution above.

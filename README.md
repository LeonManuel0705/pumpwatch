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
with a free key at one request per minute, and a single request returns every station
inside a radius. Polling that endpoint once a minute yields the same substance at full
temporal resolution for the chosen region, and the resulting dataset is genuinely first
hand. Both paths are implemented, so the archive can be folded in if access ever comes
through.

## Design decisions that matter

**Store changes, not snapshots.** Writing every station every minute would produce roughly
430,000 rows a day for this region. Writing a row only when a price or the open state
actually changes brings that down to a few thousand, which is the same compression the
MTS-K applies internally, with no loss of information.

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
interval in seconds (floored at 60, which is the API limit). Copy `regions.json.example`
to `regions.json` to rotate across several regions.

```bash
python3 scripts/test_collector.py             # collector tests, no network needed
python3 scripts/test_dump_import.py           # importer tests, no archive needed
python3 scripts/stats.py                      # rows collected, coverage, top brands
```

## Running it in Supabase instead

The collector can live in Postgres rather than on a local machine, which matters once a
front end needs to read the data: a SQLite file behind a home router is unreachable, a
Supabase table is not.

Apply in order from the SQL editor:

| file | contents |
|---|---|
| `supabase/001_schema.sql` | tables, indexes, row level security |
| `supabase/002_ingest.sql` | JSON parsing and change detection |
| `supabase/003_collector.sql` | pg_net request cycle, response pruning |
| `supabase/004_schedule.sql` | the API key and the two cron jobs |

`pg_cron` fires `collect_prices()` every minute. Because `pg_net` is asynchronous, each
run first ingests the response to the *previous* request and then issues the next one,
so the response is always a minute old and always there.

Two things keep this inside the free tier:

- **`net._http_response` must be pruned.** Every reply is stored, and at roughly 25 KB a
  minute that is about 36 MB a day. Unpruned it fills the 500 MB free database in under a
  fortnight. `prune_http_responses()` runs every ten minutes and keeps it near zero.
- **Only changes are stored.** Around 500 changed rows a day plus the poll log works out
  near 80 MB a year. Storing every reading instead would be 115,200 rows a day.

Run `supabase/test_ingest.sql` against any Postgres to check the ingest logic; it needs
neither pg_net nor pg_cron.

**Only one collector may run at a time.** The API allows one request per minute in total,
so running the Python daemon and the Supabase job together doubles the rate and gets the
key suspended.

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

The collector and the importer are written and tested. Continuous collection is running;
the analysis in question one onward needs several weeks of accumulated data before it says
anything, which is the nature of the object being studied.

## Attribution

Price data originates from the Markttransparenzstelle für Kraftstoffe (MTS-K) and is
provided by Tankerkönig under CC BY 4.0. Any published chart or claim carries that
attribution.

## License

MIT for the code. The data carries the attribution above.

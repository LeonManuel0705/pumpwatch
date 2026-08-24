# pumpwatch

Measuring how German fuel retailers actually set their prices, using a self-collected
minute-resolution dataset of every filling station within 25 km of Werder (Havel).

## Research questions

1. **Price cycles** — how many times per day does a station move its price, and how
   regular are the daily peaks and troughs (Edgeworth cycles)?
2. **Price leadership** — when a price falls, which brand moves first, and how many
   minutes pass before competitors follow? Ordering plus lag is the empirical signature
   of tacit coordination.
3. **Competition and price level** — does a station's price depend on how many rivals
   sit within 1, 3 and 5 km of it?
4. **The payoff** — what does an optimal refuelling time save a normal driver per year,
   and how much of that survives once you account for the detour?

## Why the data is collected rather than downloaded

Tankerkönig publishes a historical dump of all MTS-K price changes since 2014, but the
git repository behind it now requires a verified account. The live API is open with a
free key at one request per minute, and one request returns every station within a 25 km
radius. Polling that endpoint once a minute therefore yields the same substance at full
temporal resolution for the chosen region, and the dataset is genuinely first-hand.

## Setup

```bash
export TANKERKOENIG_API_KEY=<your key from https://onboarding.tankerkoenig.de>
python3 scripts/run_collector.py
```

No third-party dependencies: the collector uses only the Python standard library, so it
survives a year of unattended running without a dependency breaking under it.

Optional environment variables: `PUMPWATCH_DB` (database path),
`PUMPWATCH_INTERVAL` (seconds between requests, floored at 60).
Copy `regions.json.example` to `regions.json` to poll several regions in rotation.

```bash
python3 scripts/test_collector.py            # collector tests, no network needed
.venv/bin/python scripts/test_dump_import.py # importer tests, no dump needed
python3 scripts/stats.py                     # rows collected, coverage, top brands
```

## Running it permanently

The collector is meant to live on an always-on machine, not a laptop:

```bash
ssh leon@192.168.178.20
git clone <repo> pumpwatch && cd pumpwatch
setx TANKERKOENIG_API_KEY <key>
python scripts\run_collector.py
```

Register it as a service (NSSM or Task Scheduler with "run whether user is logged on or
not") so it restarts after a reboot. `poll_log` records every gap, so downtime stays
visible in the analysis instead of masquerading as an absence of price changes.

## Importing the historical dump

The MTS-K archive ships as one CSV per day under `prices/YYYY/MM/`, each row a single
price change with a second-resolution timestamp. Converting it to partitioned Parquet
makes it queryable on a laptop:

```bash
.venv/bin/python scripts/import_dump.py --source ~/tankerkoenig-data --out data/parquet
```

The importer is incremental (already-converted months are skipped), stops before the
disk fills, and normalises two things that otherwise corrupt the analysis:

- **Timestamps carry an offset** (`+01` in winter, `+02` in summer). Reading them as UTC
  shifts every summer observation one hour earlier, which would smear the daily price
  cycle exactly where it matters. Each row therefore also stores `local_time`,
  `local_hour`, `local_minute` and `local_dow` in `Europe/Berlin`.
- **A price of `0.000` means the station does not sell that fuel**, not that it is free.
  Those become NULL. On the test fixture, counting them as zero drags the mean E10 price
  from 161.4 down to 129.1 cents.

Prices are stored as integer tenths of a cent, matching the collector, so both sources
can be queried together.

## Data model

| table | contents |
|---|---|
| `stations` | master data per station, plus first and last time it was seen |
| `price_changes` | one row **only when a price or the open/closed state changes** |
| `poll_log` | every request with duration, station count and any error |

Prices are stored as integer tenths of a cent (1.719 € becomes `1719`), which keeps
change detection exact instead of relying on float comparison. A closed station reports
no prices, so its last known prices are carried forward rather than written as nulls.

Storing changes rather than snapshots keeps roughly 430,000 daily readings down to a few
thousand rows a day, which is the same compression the MTS-K itself applies.

`poll_log` exists so that data quality is auditable. Any analysis that ignores collector
downtime will systematically understate price volatility.

## Attribution

Price data originates from the Markttransparenzstelle für Kraftstoffe (MTS-K) and is
provided by Tankerkönig under CC BY 4.0. Any published chart or text must carry that
attribution.

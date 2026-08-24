import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pumpwatch.dump_import import (
    _connect, discover_months, free_bytes, import_prices_month, import_stations,
)

MIN_FREE_GB = 5


def human(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert the Tankerkoenig CSV dump to partitioned Parquet.")
    parser.add_argument("--source", required=True, type=Path, help="Path to the cloned tankerkoenig-data repo")
    parser.add_argument("--out", type=Path, default=Path("data/parquet"))
    parser.add_argument("--from-year", type=int, default=0)
    parser.add_argument("--to-year", type=int, default=9999)
    parser.add_argument("--memory-limit", default="6GB")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="Reconvert months that already exist")
    parser.add_argument("--skip-stations", action="store_true")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not (source / "prices").is_dir():
        raise SystemExit(f"No 'prices' directory under {source}. Point --source at the cloned repo root.")

    out_dir = args.out.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    months = [m for m in discover_months(source) if args.from_year <= m[0] <= args.to_year]
    if not months:
        raise SystemExit("No monthly price directories found in the given range.")

    pending = []
    for year, month in months:
        existing = out_dir / "prices" / f"year={year:04d}" / f"month={month:02d}" / "prices.parquet"
        if existing.exists() and not args.force:
            continue
        pending.append((year, month))

    print(f"source        {source}")
    print(f"destination   {out_dir}")
    print(f"months found  {len(months)}  ({months[0][0]}-{months[0][1]:02d} to {months[-1][0]}-{months[-1][1]:02d})")
    print(f"to convert    {len(pending)}  ({len(months) - len(pending)} already done)")
    print(f"free space    {human(free_bytes(out_dir))}\n")

    if not pending and args.skip_stations:
        print("Nothing to do.")
        return

    connection = _connect(args.memory_limit, args.threads)
    total_rows = 0
    total_bytes = 0
    started = time.monotonic()

    for index, (year, month) in enumerate(pending, start=1):
        if free_bytes(out_dir) < MIN_FREE_GB * 1024**3:
            print(f"\nStopping: less than {MIN_FREE_GB}GB free. Converted months are kept.")
            break
        result = import_prices_month(connection, source, out_dir, year, month)
        total_rows += result.rows
        total_bytes += result.bytes_written
        elapsed = time.monotonic() - started
        print(f"[{index:3d}/{len(pending)}] {year}-{month:02d}  "
              f"{result.rows:>10,} rows  {human(result.bytes_written):>8}  "
              f"({elapsed:.0f}s elapsed)")

    if not args.skip_stations:
        count = import_stations(connection, source, out_dir)
        print(f"\nstations      {count:,} unique")

    print(f"\ntotal         {total_rows:,} price changes, {human(total_bytes)} of Parquet")
    print(f"took          {time.monotonic() - started:.0f}s")


if __name__ == "__main__":
    main()

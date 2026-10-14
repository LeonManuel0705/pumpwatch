import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pumpwatch.collector import MIN_REQUEST_SPACING_SECONDS
from pumpwatch.config import Settings
from pumpwatch.storage import Storage


def main() -> None:
    settings = Settings.load()
    storage = Storage(settings.db_path)
    stats = storage.stats()
    row = storage.connection.execute(
        "SELECT MIN(observed_at), MAX(observed_at) FROM price_changes"
    ).fetchone()

    print(f"database      {settings.db_path}")
    print(f"stations      {stats['stations']:,}")
    print(f"changes       {stats['price_changes']:,}")
    print(f"polls         {stats['polls']:,}  ({stats['failed_polls']:,} failed)")

    if row and row[0]:
        first = datetime.fromtimestamp(row[0], timezone.utc)
        last = datetime.fromtimestamp(row[1], timezone.utc)
        days = max((row[1] - row[0]) / 86400, 1 / 24)
        spacing = max(settings.poll_interval_seconds, MIN_REQUEST_SPACING_SECONDS)
        expected = int(days * 86400 / spacing)
        coverage = 100 * stats["polls"] / expected if expected else 0
        print(f"covering      {first:%Y-%m-%d %H:%M} to {last:%Y-%m-%d %H:%M} UTC ({days:.1f} days)")
        print(f"completeness  {coverage:.1f}% of expected polls")

    brands = storage.connection.execute(
        """
        SELECT brand, COUNT(*) FROM stations
        WHERE brand != '' GROUP BY brand ORDER BY COUNT(*) DESC LIMIT 8
        """
    ).fetchall()
    if brands:
        print("\ntop brands")
        for brand, count in brands:
            print(f"  {count:4d}  {brand}")
    storage.close()


if __name__ == "__main__":
    main()

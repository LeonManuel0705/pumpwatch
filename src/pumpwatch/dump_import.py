import shutil
from dataclasses import dataclass
from pathlib import Path

import duckdb

PRICE_COLUMNS = {
    "date": "VARCHAR",
    "station_uuid": "VARCHAR",
    "diesel": "DOUBLE",
    "e5": "DOUBLE",
    "e10": "DOUBLE",
    "dieselchange": "INTEGER",
    "e5change": "INTEGER",
    "e10change": "INTEGER",
}

STATION_COLUMNS = {
    "uuid": "VARCHAR",
    "name": "VARCHAR",
    "brand": "VARCHAR",
    "street": "VARCHAR",
    "house_number": "VARCHAR",
    "post_code": "VARCHAR",
    "city": "VARCHAR",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "first_active": "VARCHAR",
    "openingtimes_json": "VARCHAR",
}


@dataclass
class MonthResult:
    year: int
    month: int
    rows: int
    bytes_written: int


def _connect(memory_limit: str, threads: int) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect()
    connection.execute(f"SET memory_limit='{memory_limit}'")
    connection.execute(f"SET threads={threads}")
    return connection


def discover_months(source: Path) -> list[tuple[int, int]]:
    months = set()
    for csv_path in (source / "prices").glob("*/*/*.csv"):
        try:
            months.add((int(csv_path.parent.parent.name), int(csv_path.parent.name)))
        except ValueError:
            continue
    return sorted(months)


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def import_prices_month(
    connection: duckdb.DuckDBPyConnection,
    source: Path,
    out_dir: Path,
    year: int,
    month: int,
) -> MonthResult:
    pattern = str(source / "prices" / f"{year:04d}" / f"{month:02d}" / "*.csv")
    target = out_dir / "prices" / f"year={year:04d}" / f"month={month:02d}"
    target.mkdir(parents=True, exist_ok=True)
    target_file = target / "prices.parquet"

    columns = ", ".join(f"'{name}': '{sql_type}'" for name, sql_type in PRICE_COLUMNS.items())
    connection.execute(
        f"""
        COPY (
            SELECT
                station_uuid,
                CAST(date AS TIMESTAMPTZ)                                  AS changed_at,
                NULLIF(CAST(round(e5     * 1000) AS INTEGER), 0)           AS e5,
                NULLIF(CAST(round(e10    * 1000) AS INTEGER), 0)           AS e10,
                NULLIF(CAST(round(diesel * 1000) AS INTEGER), 0)           AS diesel,
                e5change, e10change, dieselchange,
                CAST(date AS TIMESTAMPTZ) AT TIME ZONE 'Europe/Berlin'     AS local_time,
                EXTRACT(hour   FROM (CAST(date AS TIMESTAMPTZ) AT TIME ZONE 'Europe/Berlin')) AS local_hour,
                EXTRACT(minute FROM (CAST(date AS TIMESTAMPTZ) AT TIME ZONE 'Europe/Berlin')) AS local_minute,
                EXTRACT(dow    FROM (CAST(date AS TIMESTAMPTZ) AT TIME ZONE 'Europe/Berlin')) AS local_dow
            FROM read_csv('{pattern}', header=true, columns={{{columns}}}, ignore_errors=false)
        ) TO '{target_file}' (FORMAT parquet, COMPRESSION zstd)
        """
    )
    rows = connection.execute(f"SELECT COUNT(*) FROM read_parquet('{target_file}')").fetchone()[0]
    return MonthResult(year, month, rows, target_file.stat().st_size)


def import_stations(connection: duckdb.DuckDBPyConnection, source: Path, out_dir: Path) -> int:
    pattern = str(source / "stations" / "*" / "*" / "*.csv")
    target_file = out_dir / "stations.parquet"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    columns = ", ".join(f"'{name}': '{sql_type}'" for name, sql_type in STATION_COLUMNS.items())
    connection.execute(
        f"""
        COPY (
            SELECT uuid AS station_uuid, name, brand, street, house_number,
                   post_code, city, latitude, longitude, first_active
            FROM (
                SELECT *, row_number() OVER (PARTITION BY uuid ORDER BY filename DESC) AS recency
                FROM read_csv('{pattern}', header=true, columns={{{columns}}},
                              ignore_errors=true, filename=true)
            )
            WHERE recency = 1
        ) TO '{target_file}' (FORMAT parquet, COMPRESSION zstd)
        """
    )
    return connection.execute(f"SELECT COUNT(*) FROM read_parquet('{target_file}')").fetchone()[0]

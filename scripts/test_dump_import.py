import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import duckdb

from pumpwatch.dump_import import _connect, discover_months, import_prices_month, import_stations

PRICES_JAN = """date,station_uuid,diesel,e5,e10,dieselchange,e5change,e10change
2023-01-01 00:00:10+01,aaaaaaaa-0000-0000-0000-000000000001,1.859,1.719,1.659,1,1,1
2023-01-01 08:15:00+01,aaaaaaaa-0000-0000-0000-000000000002,1.879,1.739,0.000,1,1,2
2023-01-01 19:45:33+01,aaaaaaaa-0000-0000-0000-000000000001,1.799,1.669,1.609,1,1,1
"""

PRICES_JUL = """date,station_uuid,diesel,e5,e10,dieselchange,e5change,e10change
2023-07-01 12:00:00+02,aaaaaaaa-0000-0000-0000-000000000001,1.759,1.629,1.569,1,1,1
"""

STATIONS = """uuid,name,brand,street,house_number,post_code,city,latitude,longitude,first_active,openingtimes_json
aaaaaaaa-0000-0000-0000-000000000001,Star Werder,STAR,Chaussee,1,14542,Werder,52.3785,12.9337,2014-06-08 00:00:00,{}
aaaaaaaa-0000-0000-0000-000000000002,Aral Potsdam,ARAL,Zeppelinstr,10,14471,Potsdam,52.3906,13.0645,2014-06-08 00:00:00,{}
"""


def build_fixture(root: Path) -> None:
    (root / "prices" / "2023" / "01").mkdir(parents=True)
    (root / "prices" / "2023" / "07").mkdir(parents=True)
    (root / "stations" / "2023" / "01").mkdir(parents=True)
    (root / "prices" / "2023" / "01" / "2023-01-01-prices.csv").write_text(PRICES_JAN)
    (root / "prices" / "2023" / "07" / "2023-07-01-prices.csv").write_text(PRICES_JUL)
    (root / "stations" / "2023" / "01" / "2023-01-01-stations.csv").write_text(STATIONS)


def main() -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        source, out_dir = tmp / "dump", tmp / "parquet"
        build_fixture(source)

        assert discover_months(source) == [(2023, 1), (2023, 7)]

        connection = _connect("2GB", 2)
        january = import_prices_month(connection, source, out_dir, 2023, 1)
        import_prices_month(connection, source, out_dir, 2023, 7)
        station_count = import_stations(connection, source, out_dir)
        assert january.rows == 3
        assert station_count == 2
        print("  ok  csv converts to partitioned parquet")

        con = duckdb.connect()
        pattern = str(out_dir / "prices" / "**" / "*.parquet")
        rows = con.sql(
            f"SELECT local_time, local_hour, e5, e10 FROM read_parquet('{pattern}') ORDER BY changed_at"
        ).fetchall()

        by_local = {str(r[0]): r for r in rows}
        assert by_local["2023-01-01 00:00:10"][1] == 0, "CET midnight must stay hour 0"
        assert by_local["2023-07-01 12:00:00"][1] == 12, "CEST noon must be 12, not 10 UTC"
        print("  ok  local hour survives the CET/CEST switch")

        assert by_local["2023-01-01 08:15:00"][3] is None, "0.000 means the fuel is not sold"
        assert by_local["2023-01-01 08:15:00"][2] == 1739
        print("  ok  unavailable fuel is NULL instead of a zero price")

        joined = con.sql(
            f"""
            SELECT s.brand, count(*) FROM read_parquet('{pattern}') p
            JOIN read_parquet('{out_dir / "stations.parquet"}') s USING (station_uuid)
            GROUP BY s.brand ORDER BY s.brand
            """
        ).fetchall()
        assert joined == [("ARAL", 1), ("STAR", 3)], joined
        print("  ok  prices join to station master data")
        print("\n4 checks passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

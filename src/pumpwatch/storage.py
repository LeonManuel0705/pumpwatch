import sqlite3
from pathlib import Path

from .api import StationReading

SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
    station_id   TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    brand        TEXT NOT NULL,
    street       TEXT NOT NULL,
    house_number TEXT NOT NULL,
    post_code    TEXT NOT NULL,
    place        TEXT NOT NULL,
    lat          REAL NOT NULL,
    lng          REAL NOT NULL,
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS price_changes (
    station_id  TEXT NOT NULL,
    observed_at INTEGER NOT NULL,
    e5          INTEGER,
    e10         INTEGER,
    diesel      INTEGER,
    is_open     INTEGER NOT NULL,
    PRIMARY KEY (station_id, observed_at)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_price_changes_time ON price_changes (observed_at);

CREATE TABLE IF NOT EXISTS poll_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    region        TEXT NOT NULL,
    started_at    INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL,
    station_count INTEGER NOT NULL,
    change_count  INTEGER NOT NULL,
    ok            INTEGER NOT NULL,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_poll_log_time ON poll_log (started_at);
"""


class Storage:
    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(db_path, timeout=30)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def load_last_state(self) -> dict[str, tuple[int | None, int | None, int | None, int]]:
        """Latest known state per station, so a restart does not log phantom changes."""
        rows = self.connection.execute(
            """
            SELECT p.station_id, p.e5, p.e10, p.diesel, p.is_open
            FROM price_changes p
            JOIN (
                SELECT station_id, MAX(observed_at) AS observed_at
                FROM price_changes GROUP BY station_id
            ) latest
              ON latest.station_id = p.station_id AND latest.observed_at = p.observed_at
            """
        ).fetchall()
        return {row[0]: (row[1], row[2], row[3], row[4]) for row in rows}

    def upsert_stations(self, readings: list[StationReading], now: int) -> None:
        self.connection.executemany(
            """
            INSERT INTO stations (station_id, name, brand, street, house_number,
                                  post_code, place, lat, lng, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(station_id) DO UPDATE SET
                name = excluded.name,
                brand = excluded.brand,
                street = excluded.street,
                house_number = excluded.house_number,
                post_code = excluded.post_code,
                place = excluded.place,
                lat = excluded.lat,
                lng = excluded.lng,
                last_seen = excluded.last_seen
            """,
            [
                (r.station_id, r.name, r.brand, r.street, r.house_number,
                 r.post_code, r.place, r.lat, r.lng, now, now)
                for r in readings
            ],
        )

    def insert_changes(self, changes: list[tuple[str, int, int | None, int | None, int | None, int]]) -> None:
        self.connection.executemany(
            """
            INSERT OR IGNORE INTO price_changes (station_id, observed_at, e5, e10, diesel, is_open)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            changes,
        )

    def log_poll(self, region: str, started_at: int, duration_ms: int,
                 station_count: int, change_count: int, ok: bool, error: str | None) -> None:
        self.connection.execute(
            """
            INSERT INTO poll_log (region, started_at, duration_ms, station_count, change_count, ok, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (region, started_at, duration_ms, station_count, change_count, int(ok), error),
        )

    def commit(self) -> None:
        self.connection.commit()

    def stats(self) -> dict[str, int]:
        cursor = self.connection.execute("SELECT COUNT(*) FROM stations")
        stations = cursor.fetchone()[0]
        changes = self.connection.execute("SELECT COUNT(*) FROM price_changes").fetchone()[0]
        polls = self.connection.execute("SELECT COUNT(*) FROM poll_log").fetchone()[0]
        failed = self.connection.execute("SELECT COUNT(*) FROM poll_log WHERE ok = 0").fetchone()[0]
        return {"stations": stations, "price_changes": changes, "polls": polls, "failed_polls": failed}

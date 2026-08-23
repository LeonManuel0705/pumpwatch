import logging
import signal
import time

from .api import ApiError, StationReading, fetch_region
from .config import Region, Settings
from .storage import Storage

log = logging.getLogger(__name__)

MIN_REQUEST_SPACING_SECONDS = 60
MAX_BACKOFF_SECONDS = 900

StationState = tuple[int | None, int | None, int | None, int]


def merge_state(previous: StationState | None, reading: StationReading) -> StationState:
    """A closed station reports no prices, so the last known price is carried forward."""
    prev_e5, prev_e10, prev_diesel = (previous[0], previous[1], previous[2]) if previous else (None, None, None)
    return (
        reading.e5 if reading.e5 is not None else prev_e5,
        reading.e10 if reading.e10 is not None else prev_e10,
        reading.diesel if reading.diesel is not None else prev_diesel,
        int(reading.is_open),
    )


def detect_changes(
    state: dict[str, StationState],
    readings: list[StationReading],
    observed_at: int,
) -> list[tuple[str, int, int | None, int | None, int | None, int]]:
    changes = []
    for reading in readings:
        previous = state.get(reading.station_id)
        current = merge_state(previous, reading)
        if previous == current:
            continue
        state[reading.station_id] = current
        changes.append((reading.station_id, observed_at, current[0], current[1], current[2], current[3]))
    return changes


class Collector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.storage = Storage(settings.db_path)
        self.state = self.storage.load_last_state()
        self.running = True
        self.backoff = 0
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, *_args) -> None:
        log.info("shutdown requested, finishing current cycle")
        self.running = False

    def poll_once(self, region: Region) -> int:
        started_at = int(time.time())
        start = time.monotonic()
        try:
            readings = fetch_region(
                self.settings.api_key, region.lat, region.lng, region.radius_km,
                timeout=self.settings.request_timeout_seconds,
            )
        except ApiError as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            self.storage.log_poll(region.name, started_at, duration_ms, 0, 0, False, str(exc))
            self.storage.commit()
            log.warning("poll failed for %s: %s", region.name, exc)
            self.backoff = min(max(self.backoff * 2, 60), MAX_BACKOFF_SECONDS)
            return 0

        changes = detect_changes(self.state, readings, started_at)
        self.storage.upsert_stations(readings, started_at)
        self.storage.insert_changes(changes)
        duration_ms = int((time.monotonic() - start) * 1000)
        self.storage.log_poll(region.name, started_at, duration_ms, len(readings), len(changes), True, None)
        self.storage.commit()
        self.backoff = 0
        log.info("%s: %d stations, %d changes", region.name, len(readings), len(changes))
        return len(changes)

    def run(self) -> None:
        regions = self.settings.regions
        spacing = max(self.settings.poll_interval_seconds, MIN_REQUEST_SPACING_SECONDS)
        log.info("collecting %d region(s) every %ds", len(regions), spacing)
        index = 0
        while self.running:
            cycle_start = time.monotonic()
            self.poll_once(regions[index % len(regions)])
            index += 1
            wait = spacing + self.backoff - (time.monotonic() - cycle_start)
            deadline = time.monotonic() + max(wait, 1.0)
            while self.running and time.monotonic() < deadline:
                time.sleep(min(1.0, deadline - time.monotonic()))
        self.storage.close()
        log.info("collector stopped")

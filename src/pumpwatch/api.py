import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

BASE_URL = "https://creativecommons.tankerkoenig.de/json/list.php"
USER_AGENT = "pumpwatch/1.0 (research project; non-commercial)"

log = logging.getLogger(__name__)


class ApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class StationReading:
    station_id: str
    name: str
    brand: str
    street: str
    house_number: str
    post_code: str
    place: str
    lat: float
    lng: float
    is_open: bool
    e5: int | None
    e10: int | None
    diesel: int | None


def _to_tenth_cents(value) -> int | None:
    """Prices arrive as euro floats (1.719). Integers avoid float drift in change detection."""
    if value is None or value is False or value == "":
        return None
    try:
        return int(round(float(value) * 1000))
    except (TypeError, ValueError):
        return None


def _parse_station(raw: dict) -> StationReading | None:
    station_id = raw.get("id")
    if not station_id:
        return None
    return StationReading(
        station_id=str(station_id),
        name=str(raw.get("name") or "").strip(),
        brand=str(raw.get("brand") or "").strip(),
        street=str(raw.get("street") or "").strip(),
        house_number=str(raw.get("houseNumber") or "").strip(),
        post_code=str(raw.get("postCode") or "").strip(),
        place=str(raw.get("place") or "").strip(),
        lat=float(raw.get("lat") or 0.0),
        lng=float(raw.get("lng") or 0.0),
        is_open=bool(raw.get("isOpen")),
        e5=_to_tenth_cents(raw.get("e5")),
        e10=_to_tenth_cents(raw.get("e10")),
        diesel=_to_tenth_cents(raw.get("diesel")),
    )


def parse_response(payload: dict) -> list[StationReading]:
    if not payload.get("ok", False):
        raise ApiError(payload.get("message") or "API reported a failure")
    readings = []
    for raw in payload.get("stations") or []:
        reading = _parse_station(raw)
        if reading is not None:
            readings.append(reading)
    return readings


def fetch_region(api_key: str, lat: float, lng: float, radius_km: float, timeout: int = 30) -> list[StationReading]:
    query = urllib.parse.urlencode(
        {
            "lat": f"{lat:.5f}",
            "lng": f"{lng:.5f}",
            "rad": f"{radius_km:g}",
            "sort": "dist",
            "type": "all",
            "apikey": api_key,
        }
    )
    request = urllib.request.Request(f"{BASE_URL}?{query}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ApiError(f"HTTP {exc.code} from Tankerkoenig") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"network error: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise ApiError("response was not valid JSON") from exc
    return parse_response(payload)

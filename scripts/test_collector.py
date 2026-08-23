import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pumpwatch.api import StationReading, parse_response
from pumpwatch.collector import detect_changes
from pumpwatch.storage import Storage


def reading(station_id, e5, e10, diesel, is_open=True):
    return StationReading(
        station_id=station_id, name="Test", brand="ARAL", street="Hauptstr",
        house_number="1", post_code="14542", place="Werder", lat=52.4, lng=12.9,
        is_open=is_open, e5=e5, e10=e10, diesel=diesel,
    )


def test_only_changes_are_recorded():
    state = {}
    first = detect_changes(state, [reading("a", 1719, 1659, 1559)], 1000)
    assert len(first) == 1, "first observation must be recorded"
    same = detect_changes(state, [reading("a", 1719, 1659, 1559)], 1060)
    assert same == [], "unchanged prices must not be recorded"
    moved = detect_changes(state, [reading("a", 1699, 1659, 1559)], 1120)
    assert len(moved) == 1 and moved[0][2] == 1699


def test_closed_station_keeps_last_price():
    state = {}
    detect_changes(state, [reading("a", 1719, 1659, 1559)], 1000)
    closed = detect_changes(state, [reading("a", None, None, None, is_open=False)], 1060)
    assert len(closed) == 1, "the open/closed switch is itself a state change"
    assert closed[0][2:5] == (1719, 1659, 1559), "prices must be carried forward, not nulled"
    reopened = detect_changes(state, [reading("a", 1719, 1659, 1559, is_open=True)], 1120)
    assert len(reopened) == 1 and reopened[0][5] == 1


def test_restart_does_not_duplicate():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        storage = Storage(db_path)
        state = storage.load_last_state()
        changes = detect_changes(state, [reading("a", 1719, 1659, 1559)], 1000)
        storage.insert_changes(changes)
        storage.commit()
        storage.close()

        storage = Storage(db_path)
        restored = storage.load_last_state()
        assert restored["a"] == (1719, 1659, 1559, 1), "state must survive a restart"
        after = detect_changes(restored, [reading("a", 1719, 1659, 1559)], 1060)
        assert after == [], "restart must not log a phantom change"
        storage.close()


def test_price_parsing_and_error_response():
    payload = {
        "ok": True,
        "stations": [
            {"id": "x", "name": "A", "brand": "SHELL", "street": "S", "houseNumber": "2",
             "postCode": 14542, "place": "Werder", "lat": 52.4, "lng": 12.9,
             "isOpen": True, "e5": 1.719, "e10": False, "diesel": 1.559}
        ],
    }
    parsed = parse_response(payload)
    assert parsed[0].e5 == 1719, "euro floats must become integer tenths of a cent"
    assert parsed[0].e10 is None, "false means the station does not sell that fuel"
    assert parsed[0].post_code == "14542"

    try:
        parse_response({"ok": False, "message": "apikey nicht angegeben"})
    except Exception as exc:
        assert "apikey" in str(exc)
    else:
        raise AssertionError("a failed response must raise")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)} tests passed")

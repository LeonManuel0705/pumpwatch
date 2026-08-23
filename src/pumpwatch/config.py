import json
import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "pumpwatch.db"


@dataclass(frozen=True)
class Region:
    name: str
    lat: float
    lng: float
    radius_km: float = 25.0


@dataclass(frozen=True)
class Settings:
    api_key: str
    db_path: Path = DEFAULT_DB_PATH
    poll_interval_seconds: int = 60
    request_timeout_seconds: int = 30
    regions: tuple[Region, ...] = field(
        default_factory=lambda: (Region("werder-potsdam", 52.3785, 12.9337),)
    )

    @classmethod
    def load(cls) -> "Settings":
        api_key = os.environ.get("TANKERKOENIG_API_KEY", "").strip()
        if not api_key:
            raise SystemExit(
                "TANKERKOENIG_API_KEY is not set. Request a key at "
                "https://onboarding.tankerkoenig.de and export it before starting."
            )

        config_path = PROJECT_ROOT / "regions.json"
        regions = cls.__dataclass_fields__["regions"].default_factory()
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            regions = tuple(Region(**entry) for entry in raw)

        db_path = Path(os.environ.get("PUMPWATCH_DB", DEFAULT_DB_PATH))
        interval = int(os.environ.get("PUMPWATCH_INTERVAL", "60"))
        return cls(
            api_key=api_key,
            db_path=db_path,
            poll_interval_seconds=interval,
            regions=regions,
        )

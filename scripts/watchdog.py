import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STALE_AFTER_MINUTES = 30


def load_env() -> dict[str, str]:
    values = dict(os.environ)
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and re.fullmatch(r"[A-Z_][A-Z0-9_]*", key.strip()):
                values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def parse_timestamp(raw: str) -> datetime:
    """PostgREST emits a variable number of fractional digits, which older fromisoformat rejects."""
    return datetime.fromisoformat(re.sub(r"\.\d+", "", raw))


def fetch_health(url: str, key: str) -> dict:
    headers = {"apikey": key, "Accept": "application/json"}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(f"{url.rstrip('/')}/rest/v1/collector_health?select=*", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.loads(response.read().decode("utf-8"))
    if not rows:
        raise RuntimeError("collector_health returned no row")
    return rows[0]


def check(env: dict[str, str]) -> str | None:
    url, key = env.get("SUPABASE_URL"), env.get("SUPABASE_ANON_KEY")
    if not url or not key:
        return "SUPABASE_URL oder SUPABASE_ANON_KEY fehlt in .env"
    try:
        health = fetch_health(url, key)
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        return f"Supabase nicht erreichbar ({exc})"

    last_success = health.get("last_success")
    if not last_success:
        return f"Seit 24 Stunden kein erfolgreicher Abruf. Letzter Fehler: {health.get('last_error') or 'keiner'}"
    minutes = (datetime.now(timezone.utc) - parse_timestamp(last_success)).total_seconds() / 60
    if minutes > STALE_AFTER_MINUTES:
        return f"Letzter erfolgreicher Abruf vor {minutes:.0f} Minuten. Letzter Fehler: {health.get('last_error') or 'keiner'}"

    print(
        f"{datetime.now():%Y-%m-%d %H:%M} ok, last success {minutes:.0f} min ago, "
        f"{health.get('polls_last_hour')} polls in the last hour, {health.get('changes_24h')} changes in 24 h, "
        f"{health.get('failures_24h')} failures in 24 h, price table {health.get('price_table_size')}"
    )
    return None


def notify(message: str) -> None:
    subprocess.run(
        ["osascript", "-e", "on run argv", "-e",
         'display notification (item 1 of argv) with title "pumpwatch sammelt nicht"', "-e", "end run", message],
        check=False,
    )


def main() -> int:
    problem = check(load_env())
    if problem is None:
        return 0
    print(f"{datetime.now():%Y-%m-%d %H:%M} PROBLEM {problem}")
    if sys.platform == "darwin":
        notify(problem)
    return 1


if __name__ == "__main__":
    sys.exit(main())

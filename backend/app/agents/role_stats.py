import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STATS_PATH = Path(__file__).resolve().parents[2] / "data" / "role_stats.json"
_ACTIVE_WINDOW_SECONDS = 300


def _load() -> dict[str, Any]:
    try:
        return json.loads(_STATS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(stats: dict[str, Any]) -> None:
    _STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def record_role_selection(keys: list[str]) -> None:
    if not keys:
        return
    stats = _load()
    now = datetime.now(timezone.utc).isoformat()
    for key in keys:
        entry = stats.get(key, {"run_count": 0, "last_run_at": None})
        entry["run_count"] = entry.get("run_count", 0) + 1
        entry["last_run_at"] = now
        stats[key] = entry
    _save(stats)


def get_role_stats() -> dict[str, dict[str, Any]]:
    stats = _load()
    now = datetime.now(timezone.utc)
    for key, entry in stats.items():
        last = entry.get("last_run_at")
        if last:
            try:
                delta = (now - datetime.fromisoformat(last)).total_seconds()
                entry["active"] = delta < _ACTIVE_WINDOW_SECONDS
                entry["seconds_ago"] = int(delta)
            except ValueError:
                entry["active"] = False
                entry["seconds_ago"] = None
        else:
            entry["active"] = False
            entry["seconds_ago"] = None
    return stats

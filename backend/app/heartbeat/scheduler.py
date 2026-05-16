import asyncio
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.briefs.rss_brief import generate_morning_brief
from app.config import settings
from app.integrations.gmail_client import GmailIntegrationError, list_gmail_messages


class HeartbeatError(Exception):
    """Raised when Eva cannot run or inspect heartbeat jobs."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
HEARTBEATS_PATH = DATA_DIR / "eva_heartbeats.json"
HEARTBEATS_EXAMPLE_PATH = DATA_DIR / "eva_heartbeats.example.json"
HEARTBEAT_STATE_PATH = DATA_DIR / "eva_heartbeat_state.json"


def ensure_heartbeats_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if HEARTBEATS_PATH.exists():
        return
    if HEARTBEATS_EXAMPLE_PATH.exists():
        shutil.copyfile(HEARTBEATS_EXAMPLE_PATH, HEARTBEATS_PATH)
    else:
        HEARTBEATS_PATH.write_text(json.dumps({"jobs": []}, indent=2), encoding="utf-8")


def load_heartbeats() -> list[dict[str, Any]]:
    ensure_heartbeats_file()
    try:
        payload = json.loads(HEARTBEATS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HeartbeatError("data/eva_heartbeats.json contient du JSON invalide.") from exc
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        raise HeartbeatError("Le champ jobs doit etre une liste.")
    return [job for job in jobs if isinstance(job, dict)]


def _load_state() -> dict[str, Any]:
    if not HEARTBEAT_STATE_PATH.exists():
        return {"runs": {}}
    try:
        state = json.loads(HEARTBEAT_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"runs": {}}
    return state if isinstance(state, dict) else {"runs": {}}


def _save_state(state: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HEARTBEAT_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def heartbeat_status() -> dict[str, Any]:
    jobs = load_heartbeats()
    state = _load_state()
    return {
        "enabled": settings.eva_heartbeat_enabled,
        "poll_seconds": settings.eva_heartbeat_poll_seconds,
        "jobs": jobs,
        "state": state,
    }


async def run_heartbeat_job(job_key: str) -> dict[str, Any]:
    jobs = load_heartbeats()
    job = next((item for item in jobs if str(item.get("key")) == job_key), None)
    if not job:
        raise HeartbeatError(f"Heartbeat introuvable: {job_key}")

    if job_key == "morning_brief":
        brief = await generate_morning_brief()
        result = f"Brief genere: {brief.title}"
    elif job_key == "inbox_triage":
        try:
            messages = list_gmail_messages(max_results=5)
            result = f"{len(messages)} mails recents lus pour triage."
        except GmailIntegrationError as exc:
            result = f"Gmail non disponible pour le triage: {exc}"
    elif job_key == "end_of_day_log":
        result = "Journal du soir prepare: recap manuel a completer dans le chat."
    else:
        result = "Heartbeat placeholder execute sans action externe."

    now = datetime.now()
    state = _load_state()
    runs = state.setdefault("runs", {})
    runs[job_key] = {
        "last_run_at": now.isoformat(timespec="seconds"),
        "last_run_date": now.date().isoformat(),
        "last_result": result,
    }
    _save_state(state)

    return {
        "job": job,
        "result": result,
    }


async def _run_due_jobs_once() -> None:
    now = datetime.now()
    today = now.date().isoformat()
    state = _load_state()
    runs = state.setdefault("runs", {})

    for job in load_heartbeats():
        if not bool(job.get("enabled", False)):
            continue

        job_key = str(job.get("key", "")).strip()
        scheduled_time = str(job.get("time", "")).strip()
        last_run_date = runs.get(job_key, {}).get("last_run_date")
        if not job_key or not scheduled_time or last_run_date == today:
            continue

        try:
            scheduled = datetime.strptime(scheduled_time, "%H:%M").time()
        except ValueError:
            continue

        if now.time() >= scheduled:
            await run_heartbeat_job(job_key)


async def heartbeat_loop() -> None:
    while True:
        if settings.eva_heartbeat_enabled:
            try:
                await _run_due_jobs_once()
            except Exception:
                pass

        await asyncio.sleep(max(settings.eva_heartbeat_poll_seconds, 15))


def start_heartbeat_background_task() -> asyncio.Task[None] | None:
    if not settings.eva_heartbeat_enabled:
        return None
    return asyncio.create_task(heartbeat_loop())

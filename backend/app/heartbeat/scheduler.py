import asyncio
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.briefs.smart_brief import generate_smart_morning_brief
from app.config import settings
from app.integrations.gmail_auto_reply import GmailAutoReplyError, run_gmail_auto_reply_once
from app.integrations.gmail_client import GmailIntegrationError, list_gmail_messages
from app.integrations.google_calendar_client import list_calendar_events


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


def _push_if_available(source: str, content: str, kind: str = "info") -> None:
    try:
        from app.proactive.store import push_proactive
        push_proactive(source, content, kind)
    except Exception:
        pass


async def run_heartbeat_job(job_key: str) -> dict[str, Any]:
    jobs = load_heartbeats()
    job = next((item for item in jobs if str(item.get("key")) == job_key), None)
    if not job:
        raise HeartbeatError(f"Heartbeat introuvable: {job_key}")

    if job_key == "morning_brief":
        brief = await generate_smart_morning_brief()
        result = f"Brief genere: {brief.title}"
        _push_if_available(
            "morning_brief",
            f"**Brief du matin**\n\n{brief.content or brief.title}",
            "brief",
        )
    elif job_key == "inbox_triage":
        try:
            from app.integrations.email_autonomous_triage import (
                build_triage_proactive_message,
                run_autonomous_triage,
            )
            report = await run_autonomous_triage(max_emails=5)
            drafted = report.get("drafted_count", 0)
            checked = report.get("checked", 0)
            result = f"Triage autonome: {checked} email(s) verifie(s), {drafted} brouillon(s) cree(s)."
            proactive_msg = build_triage_proactive_message(report)
            _push_if_available("inbox_triage", proactive_msg, "gmail")
        except Exception as exc:
            result = f"Triage autonome indisponible: {exc}"
    elif job_key == "gmail_auto_reply":
        try:
            report = await run_gmail_auto_reply_once()
            result = (
                f"Auto-reponses Gmail: {report.get('sent_count', 0)} envoyees, "
                f"{report.get('drafted_count', 0)} brouillons, "
                f"{report.get('skipped_count', 0)} ignorees. "
                f"Statut: {report.get('status')}."
            )
            if report.get("reason"):
                result = f"{result} {report['reason']}"
            sent = report.get("sent_count", 0)
            drafted = report.get("drafted_count", 0)
            if sent > 0 or drafted > 0:
                _push_if_available(
                    "gmail_auto_reply",
                    f"**Auto-reponses Gmail** — {sent} envoyee(s), {drafted} brouillon(s) cree(s).",
                    "gmail",
                )
        except (GmailIntegrationError, GmailAutoReplyError) as exc:
            result = f"Auto-reponses Gmail indisponibles: {exc}"
    elif job_key == "calendar_check":
        try:
            now = datetime.now()
            events = list_calendar_events(days=1, max_results=10)
            upcoming = []
            for event in events:
                start_str = event.get("start", {})
                if isinstance(start_str, dict):
                    dt_str = start_str.get("dateTime") or start_str.get("date", "")
                else:
                    dt_str = str(start_str)
                try:
                    from datetime import timezone
                    event_dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    local_dt = event_dt.astimezone().replace(tzinfo=None)
                    delta_min = (local_dt - now).total_seconds() / 60
                    if 0 < delta_min <= 60:
                        upcoming.append((local_dt, event.get("summary", "Evenement"), delta_min))
                except (ValueError, TypeError):
                    pass
            if upcoming:
                lines = "\n".join(
                    f"- **{name}** dans {int(delta)}min ({dt.strftime('%H:%M')})"
                    for dt, name, delta in sorted(upcoming)
                )
                _push_if_available(
                    "calendar_check",
                    f"**Agenda** — evenement(s) proche(s):\n{lines}",
                    "calendar",
                )
            result = f"Calendrier verifie: {len(upcoming)} evenement(s) dans l'heure."
        except Exception as exc:
            result = f"Calendrier indisponible: {exc}"
    elif job_key == "end_of_day_log":
        result = "Journal du soir prepare: recap manuel a completer dans le chat."
        _push_if_available(
            "end_of_day_log",
            "**Journal du soir** — Que veux-tu noter ou cloturer aujourd'hui ?",
            "info",
        )
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
        try:
            repeat_minutes = int(job.get("repeat_minutes") or 0)
        except (TypeError, ValueError):
            repeat_minutes = 0
        last_run_at = runs.get(job_key, {}).get("last_run_at")
        last_run_date = runs.get(job_key, {}).get("last_run_date")
        if not job_key:
            continue

        if repeat_minutes > 0:
            should_run = True
            if last_run_at:
                try:
                    last_dt = datetime.fromisoformat(str(last_run_at))
                    delta_seconds = (now - last_dt).total_seconds()
                    should_run = delta_seconds >= repeat_minutes * 60
                except ValueError:
                    should_run = True
            if should_run:
                await run_heartbeat_job(job_key)
            continue

        if not scheduled_time or last_run_date == today:
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

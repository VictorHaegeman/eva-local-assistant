import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings


class JobStoreError(Exception):
    """Raised when Eva cannot read or write the local job queue."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "eva_jobs"
JOBS_RESULTS_DIR = JOBS_DIR / "results"
JOBS_STATE_PATH = JOBS_DIR / "state.json"
JOBS_EVENTS_PATH = JOBS_DIR / "events.jsonl"
JOBS_CHECKPOINTS_PATH = JOBS_DIR / "checkpoints.jsonl"

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _empty_state() -> dict[str, Any]:
    return {
        "version": 1,
        "jobs": {},
        "order": [],
        "stats": {
            "queued_total": 0,
            "completed_total": 0,
            "failed_total": 0,
            "completed_since_checkpoint": 0,
            "last_system_checkpoint_at": "",
        },
    }


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def ensure_job_store() -> None:
    JOBS_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if JOBS_STATE_PATH.exists():
        return
    _save_state(_empty_state())


def _load_state() -> dict[str, Any]:
    ensure_job_store()
    try:
        payload = json.loads(JOBS_STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobStoreError("data/eva_jobs/state.json contient du JSON invalide.") from exc
    except OSError as exc:
        raise JobStoreError("Impossible de lire la queue de jobs Eva.") from exc

    if not isinstance(payload, dict):
        return _empty_state()
    payload.setdefault("jobs", {})
    payload.setdefault("order", [])
    payload.setdefault("stats", {})
    return payload


def _save_state(state: dict[str, Any]) -> None:
    JOBS_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = JOBS_STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(JOBS_STATE_PATH)


def append_job_event(event: str, job_id: str = "", payload: dict[str, Any] | None = None) -> None:
    event_payload = {
        "created_at": _now(),
        "event": event,
        "job_id": job_id,
        "payload": payload or {},
    }
    _append_jsonl(JOBS_EVENTS_PATH, event_payload)


def checkpoint_job(job_id: str, label: str, payload: dict[str, Any] | None = None) -> None:
    checkpoint_payload = {
        "created_at": _now(),
        "job_id": job_id,
        "label": label,
        "payload": payload or {},
    }
    _append_jsonl(JOBS_CHECKPOINTS_PATH, checkpoint_payload)
    append_job_event("checkpoint", job_id, {"label": label, **(payload or {})})


def enqueue_job(
    instruction: str,
    *,
    kind: str = "chat_task",
    source: str = "api",
    priority: str = "normal",
    payload: dict[str, Any] | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    clean_instruction = " ".join(instruction.strip().split())
    if not clean_instruction:
        raise JobStoreError("Instruction de job vide.")

    job_id = f"job-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    now = _now()
    job = {
        "id": job_id,
        "kind": kind.strip() or "chat_task",
        "source": source.strip() or "api",
        "priority": priority.strip() or "normal",
        "status": "queued",
        "instruction": clean_instruction[:20_000],
        "payload": payload or {},
        "session_id": session_id.strip(),
        "attempts": 0,
        "max_attempts": max(1, settings.eva_job_runner_max_attempts),
        "created_at": now,
        "updated_at": now,
        "started_at": "",
        "completed_at": "",
        "last_error": "",
        "result_summary": "",
        "result_path": "",
    }

    with _LOCK:
        state = _load_state()
        jobs = state.setdefault("jobs", {})
        order = state.setdefault("order", [])
        jobs[job_id] = job
        order.append(job_id)
        stats = state.setdefault("stats", {})
        stats["queued_total"] = int(stats.get("queued_total") or 0) + 1
        _save_state(state)

    append_job_event("queued", job_id, {"kind": job["kind"], "source": job["source"]})
    checkpoint_job(job_id, "queued", {"instruction": clean_instruction[:500]})
    return job


def _sort_job_ids(state: dict[str, Any]) -> list[str]:
    order = [str(job_id) for job_id in state.get("order", [])]
    jobs = state.get("jobs", {})
    missing = [str(job_id) for job_id in jobs.keys() if str(job_id) not in order]
    return [*order, *missing]


def list_jobs(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = min(max(limit, 1), 300)
    with _LOCK:
        state = _load_state()
        jobs = state.get("jobs", {})
        items = [jobs[job_id] for job_id in _sort_job_ids(state) if job_id in jobs]
    if status:
        items = [job for job in items if str(job.get("status")) == status]
    return list(reversed(items[-safe_limit:]))


def get_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
        job = state.get("jobs", {}).get(job_id)
    if not isinstance(job, dict):
        raise JobStoreError(f"Job introuvable: {job_id}")
    return job


def job_runner_status() -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
        jobs = list(state.get("jobs", {}).values())
        stats = state.get("stats", {})

    counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1

    running = next((job for job in jobs if job.get("status") == "running"), None)
    return {
        "enabled": settings.eva_job_runner_enabled,
        "poll_seconds": settings.eva_job_runner_poll_seconds,
        "checkpoint_every": settings.eva_job_checkpoint_every,
        "counts": counts,
        "running": running,
        "stats": stats,
        "paths": {
            "state": str(JOBS_STATE_PATH),
            "events": str(JOBS_EVENTS_PATH),
            "checkpoints": str(JOBS_CHECKPOINTS_PATH),
            "results": str(JOBS_RESULTS_DIR),
        },
    }


def recover_running_jobs() -> int:
    recovered = 0
    with _LOCK:
        state = _load_state()
        now = _now()
        for job in state.get("jobs", {}).values():
            if job.get("status") != "running":
                continue
            job["status"] = "queued"
            job["updated_at"] = now
            job["last_error"] = "Eva a redemarre pendant ce job; reprise automatique."
            recovered += 1
        if recovered:
            _save_state(state)

    if recovered:
        append_job_event("recovered_running_jobs", payload={"count": recovered})
    return recovered


def acquire_next_job() -> dict[str, Any] | None:
    with _LOCK:
        state = _load_state()
        jobs = state.get("jobs", {})
        selected: dict[str, Any] | None = None

        if any(job.get("status") == "running" for job in jobs.values()):
            return None

        for job_id in _sort_job_ids(state):
            job = jobs.get(job_id)
            if isinstance(job, dict) and job.get("status") == "queued":
                selected = job
                break

        if not selected:
            return None

        now = _now()
        selected["status"] = "running"
        selected["attempts"] = int(selected.get("attempts") or 0) + 1
        selected["started_at"] = selected.get("started_at") or now
        selected["updated_at"] = now
        selected["last_error"] = ""
        _save_state(state)

    append_job_event("started", str(selected["id"]), {"attempt": selected["attempts"]})
    checkpoint_job(str(selected["id"]), "started", {"attempt": selected["attempts"]})
    return selected


def _write_result(job_id: str, result: dict[str, Any]) -> Path:
    JOBS_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result_path = JOBS_RESULTS_DIR / f"{job_id}.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result_path


def complete_job(job_id: str, result: dict[str, Any]) -> dict[str, Any]:
    result_path = _write_result(job_id, result)
    summary = str(result.get("summary") or result.get("message") or "Job termine.")
    with _LOCK:
        state = _load_state()
        job = state.get("jobs", {}).get(job_id)
        if not isinstance(job, dict):
            raise JobStoreError(f"Job introuvable: {job_id}")

        now = _now()
        job["status"] = "completed"
        job["updated_at"] = now
        job["completed_at"] = now
        job["result_summary"] = summary[:1000]
        job["result_path"] = str(result_path)
        stats = state.setdefault("stats", {})
        stats["completed_total"] = int(stats.get("completed_total") or 0) + 1
        stats["completed_since_checkpoint"] = int(stats.get("completed_since_checkpoint") or 0) + 1

        if int(stats["completed_since_checkpoint"]) >= max(1, settings.eva_job_checkpoint_every):
            stats["completed_since_checkpoint"] = 0
            stats["last_system_checkpoint_at"] = now
            _append_jsonl(
                JOBS_CHECKPOINTS_PATH,
                {
                    "created_at": now,
                    "job_id": "",
                    "label": "system_batch_checkpoint",
                    "payload": {
                        "completed_total": stats["completed_total"],
                        "checkpoint_every": settings.eva_job_checkpoint_every,
                    },
                },
            )

        _save_state(state)
        completed_job = dict(job)

    append_job_event("completed", job_id, {"summary": summary[:500], "result_path": str(result_path)})
    checkpoint_job(job_id, "completed", {"summary": summary[:500], "result_path": str(result_path)})
    return completed_job


def fail_job(job_id: str, error: str, *, retry: bool = True) -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
        job = state.get("jobs", {}).get(job_id)
        if not isinstance(job, dict):
            raise JobStoreError(f"Job introuvable: {job_id}")

        attempts = int(job.get("attempts") or 0)
        max_attempts = int(job.get("max_attempts") or settings.eva_job_runner_max_attempts)
        can_retry = retry and attempts < max_attempts
        now = _now()
        job["status"] = "queued" if can_retry else "failed"
        job["updated_at"] = now
        job["completed_at"] = "" if can_retry else now
        job["last_error"] = error[:3000]
        if not can_retry:
            stats = state.setdefault("stats", {})
            stats["failed_total"] = int(stats.get("failed_total") or 0) + 1
        _save_state(state)
        failed_job = dict(job)

    append_job_event(
        "retry_scheduled" if failed_job["status"] == "queued" else "failed",
        job_id,
        {"error": error[:1000], "attempts": failed_job.get("attempts"), "max_attempts": failed_job.get("max_attempts")},
    )
    checkpoint_job(job_id, "retry" if failed_job["status"] == "queued" else "failed", {"error": error[:1000]})
    return failed_job


def cancel_job(job_id: str) -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
        job = state.get("jobs", {}).get(job_id)
        if not isinstance(job, dict):
            raise JobStoreError(f"Job introuvable: {job_id}")
        if job.get("status") == "running":
            raise JobStoreError("Impossible d'annuler un job deja en cours d'execution.")
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return job
        job["status"] = "cancelled"
        job["updated_at"] = _now()
        _save_state(state)
        cancelled = dict(job)

    append_job_event("cancelled", job_id)
    checkpoint_job(job_id, "cancelled")
    return cancelled


import asyncio
from typing import Any

import httpx

from app.agents.operator_journal import OperatorJournalError, record_operator_tick
from app.cognition.output_sanitizer import sanitize_assistant_output
from app.config import settings
from app.jobs.job_store import (
    acquire_next_job,
    checkpoint_job,
    complete_job,
    ensure_job_store,
    fail_job,
    job_runner_status,
    recover_running_jobs,
)
from app.memory.chat_history_store import ChatHistoryError, append_chat_exchange


class JobWorkerError(Exception):
    """Raised when Eva cannot execute a queued job."""


async def _notify_telegram(message: str) -> None:
    token = settings.eva_telegram_bot_token.strip()
    chat_id = settings.eva_telegram_allowed_chat_id.strip()
    if not settings.eva_telegram_enabled or not token or not chat_id:
        return

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message[:3500]},
            )
    except Exception:
        pass


async def _execute_chat_job(job: dict[str, Any]) -> dict[str, Any]:
    from app.chat_service import process_chat_messages

    instruction = str(job.get("instruction", "")).strip()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        messages = [{"role": "user", "content": instruction}]

    checkpoint_job(str(job["id"]), "interpreting", {"kind": job.get("kind"), "source": job.get("source")})
    result = await process_chat_messages(
        messages,
        mode=str(payload.get("mode") or "chat"),
        trusted_actions=True,
        channel="job",
    )
    assistant_text = str(result.get("message", {}).get("content", "")).strip()
    assistant_text = sanitize_assistant_output(
        assistant_text,
        user_message=instruction,
        channel="job",
    )
    if not assistant_text:
        raise JobWorkerError("Eva n'a pas produit de reponse exploitable pour ce job.")

    checkpoint_job(str(job["id"]), "executed", {"chars": len(assistant_text)})

    try:
        append_chat_exchange(
            f"job-{job['id']}",
            instruction,
            assistant_text,
            channel="job",
        )
    except ChatHistoryError:
        pass

    try:
        record_operator_tick(
            instruction,
            assistant_text,
            channel="job",
            trusted_actions=True,
            conversation_context=[],
        )
    except OperatorJournalError:
        pass

    return {
        "summary": assistant_text[:1000],
        "message": assistant_text,
        "chat_response": result,
    }


async def execute_job(job: dict[str, Any]) -> dict[str, Any]:
    kind = str(job.get("kind") or "chat_task")
    if kind in {"chat_task", "autonomous_task", "telegram_task", "project_task"}:
        return await _execute_chat_job(job)
    raise JobWorkerError(f"Type de job non supporte: {kind}")


async def run_next_job_once() -> dict[str, Any]:
    ensure_job_store()
    job = acquire_next_job()
    if not job:
        return {"ran": False, "message": "Aucun job en attente.", "status": job_runner_status()}

    job_id = str(job["id"])
    await _notify_telegram(f"Eva lance le job {job_id}.\n{job.get('instruction', '')[:700]}")
    try:
        result = await execute_job(job)
        completed = complete_job(job_id, result)
        await _notify_telegram(
            f"Eva a termine le job {job_id}.\n"
            f"Statut: completed\n\n"
            f"{str(completed.get('result_summary', ''))[:1800]}"
        )
        return {"ran": True, "job": completed, "result": result}
    except Exception as exc:
        failed = fail_job(job_id, str(exc), retry=True)
        if failed.get("status") == "failed":
            await _notify_telegram(f"Eva n'a pas reussi le job {job_id}.\n{exc}")
        return {"ran": True, "job": failed, "error": str(exc)}


async def job_worker_loop() -> None:
    ensure_job_store()
    recover_running_jobs()
    while True:
        if settings.eva_job_runner_enabled:
            try:
                await run_next_job_once()
            except Exception:
                pass
        await asyncio.sleep(max(settings.eva_job_runner_poll_seconds, 2))


def start_job_worker_background_task() -> asyncio.Task[None] | None:
    if not settings.eva_job_runner_enabled:
        return None
    return asyncio.create_task(job_worker_loop())

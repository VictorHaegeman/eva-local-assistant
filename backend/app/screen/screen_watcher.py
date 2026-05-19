import asyncio
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.screen.screen_reader import ScreenReaderError, analyze_screen


_latest_analysis: dict[str, Any] | None = None
_latest_error: str = ""
_last_run_at: datetime | None = None
_running = False


def _now() -> datetime:
    return datetime.now(UTC)


def _age_seconds(timestamp: datetime | None) -> float | None:
    if timestamp is None:
        return None
    return max(0.0, (_now() - timestamp).total_seconds())


def screen_watcher_status() -> dict[str, object]:
    return {
        "enabled": settings.eva_screen_watch_enabled and settings.eva_screen_enabled,
        "running": _running,
        "interval_seconds": settings.eva_screen_watch_interval_seconds,
        "context_max_age_seconds": settings.eva_screen_watch_context_max_age_seconds,
        "last_run_at": _last_run_at.isoformat() if _last_run_at else None,
        "last_age_seconds": _age_seconds(_last_run_at),
        "has_latest_analysis": _latest_analysis is not None,
        "last_error": _latest_error,
    }


def latest_screen_analysis() -> dict[str, Any] | None:
    return _latest_analysis


def latest_screen_context() -> str:
    if not _latest_analysis or not _last_run_at:
        return ""

    age = _age_seconds(_last_run_at)
    if age is None or age > settings.eva_screen_watch_context_max_age_seconds:
        return ""

    analysis = str(_latest_analysis.get("analysis", "")).strip()
    if not analysis:
        return ""

    capture = _latest_analysis.get("capture", {})
    created_at = capture.get("created_at") if isinstance(capture, dict) else None
    return (
        "Contexte visuel recent de l'ecran du PC de Victor, obtenu par capture locale "
        f"et modele vision Ollama ({round(age)}s):\n"
        f"Capture: {created_at or 'date inconnue'}\n"
        f"{analysis[:1800]}"
    )


async def run_screen_watch_once() -> dict[str, Any]:
    global _latest_analysis, _latest_error, _last_run_at
    result = await analyze_screen(
        instruction=(
            "Observe l'ecran pour donner a Eva un contexte visuel permanent. "
            "Sois court. Mentionne les erreurs visibles, la page/app active et l'action probable. "
            "Ne retranscris jamais de secret."
        ),
        auto_fix=False,
    )
    _latest_analysis = result
    _latest_error = ""
    _last_run_at = _now()
    return result


async def screen_watch_loop() -> None:
    global _latest_error, _last_run_at, _running
    if not settings.eva_screen_watch_enabled or not settings.eva_screen_enabled:
        return

    _running = True
    interval = max(15, settings.eva_screen_watch_interval_seconds)
    try:
        while True:
            try:
                await run_screen_watch_once()
            except ScreenReaderError as exc:
                _latest_error = str(exc)
                _last_run_at = _now()
            except Exception as exc:
                _latest_error = f"Erreur vision continue: {exc}"
                _last_run_at = _now()
            await asyncio.sleep(interval)
    finally:
        _running = False


def start_screen_watch_background_task() -> asyncio.Task[None] | None:
    if not settings.eva_screen_watch_enabled or not settings.eva_screen_enabled:
        return None

    return asyncio.create_task(screen_watch_loop())

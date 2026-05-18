import base64
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama_vision
from app.terminal.terminal_doctor import (
    analyze_terminal_error,
    diagnosis_to_dict,
    launch_terminal_fix,
)


class ScreenReaderError(Exception):
    """Raised when Eva cannot read or analyze the local screen."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SCREEN_CAPTURE_DIR = DATA_DIR / "screen_captures"


DEFAULT_SCREEN_PROMPT = """
Tu es Eva Screen Reader. Analyse cette capture d'ecran locale du PC de Victor.

Objectif:
1. Decris ce que tu vois en 3-6 lignes.
2. Si une fenetre terminal affiche une erreur, retranscris le texte utile le plus fidelement possible.
3. Explique la cause probable.
4. Propose la prochaine action locale la plus simple.

Ne pretends pas avoir clique ou modifie quelque chose.
Ne demande pas de secret. Si tu vois un token, une cle ou un mot de passe, ne le repete pas.
""".strip()


def _pillow_available() -> bool:
    try:
        import PIL.ImageGrab  # noqa: F401
    except ImportError:
        return False
    return True


def screen_status() -> dict[str, object]:
    return {
        "enabled": settings.eva_screen_enabled,
        "capture_dir": str(SCREEN_CAPTURE_DIR),
        "pillow_available": _pillow_available(),
        "vision_model": settings.eva_screen_vision_model,
        "local_only": True,
        "captures_gitignored": True,
    }


def _cleanup_old_captures() -> None:
    max_captures = max(settings.eva_screen_max_captures, 1)
    captures = sorted(
        SCREEN_CAPTURE_DIR.glob("eva-screen-*.jpg"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_capture in captures[max_captures:]:
        try:
            old_capture.unlink()
        except OSError:
            pass


def capture_screen() -> dict[str, object]:
    if not settings.eva_screen_enabled:
        raise ScreenReaderError("Lecture d'ecran desactivee. Active EVA_SCREEN_ENABLED=true.")

    try:
        from PIL import ImageGrab
    except ImportError as exc:
        raise ScreenReaderError("Pillow est absent. Lance: pip install -r backend/requirements.txt") from exc

    SCREEN_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = SCREEN_CAPTURE_DIR / f"eva-screen-{timestamp}.jpg"

    try:
        try:
            image = ImageGrab.grab(all_screens=True)
        except TypeError:
            image = ImageGrab.grab()

        image = image.convert("RGB")
        max_width = 1600
        if image.width > max_width:
            ratio = max_width / image.width
            image = image.resize((max_width, int(image.height * ratio)))
        image.save(path, format="JPEG", quality=82, optimize=True)
    except Exception as exc:
        raise ScreenReaderError("Impossible de capturer l'ecran local.") from exc

    _cleanup_old_captures()
    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "created_at": datetime.now(UTC).isoformat(),
    }


def _encode_capture(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


async def analyze_screen(
    instruction: str = "",
    auto_fix: bool = False,
) -> dict[str, Any]:
    capture = capture_screen()
    path = Path(str(capture["path"]))
    prompt = DEFAULT_SCREEN_PROMPT
    if instruction.strip():
        prompt = f"{prompt}\n\nInstruction de Victor:\n{instruction.strip()}"

    try:
        analysis = await ask_ollama_vision(
            image_base64=_encode_capture(path),
            prompt=prompt,
            model=settings.eva_screen_vision_model,
        )
    except OllamaClientError as exc:
        raise ScreenReaderError(str(exc)) from exc

    diagnosis = analyze_terminal_error(analysis)
    launched = None
    if auto_fix and diagnosis.fix and diagnosis.fix.safe_to_launch:
        launched = launch_terminal_fix(diagnosis.fix.key)

    return {
        "capture": capture,
        "vision_model": settings.eva_screen_vision_model,
        "analysis": analysis,
        "terminal_diagnosis": diagnosis_to_dict(diagnosis),
        "launched": launched,
    }

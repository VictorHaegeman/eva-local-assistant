import json
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.integrations.desktop_automation import (
    DesktopAutomationError,
    click_pixel,
    click_ratio,
    press_hotkey,
    press_key,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama_vision
from app.screen.screen_reader import ScreenReaderError, _encode_capture, capture_screen


class VisualActionError(Exception):
    """Raised when Eva cannot infer or execute a visual desktop action."""


VISUAL_ACTION_PROMPT = """
Tu es Eva Visual Operator. Tu regardes une capture de l'ecran local du PC de Victor.

Ta mission: choisir l'action UI la plus probable pour satisfaire l'instruction.

Reponds uniquement en JSON valide, sans Markdown:
{
  "action": "click" | "hotkey" | "none",
  "target": "description courte du bouton/champ vise",
  "x_ratio": 0.0,
  "y_ratio": 0.0,
  "hotkey": "ctrl+v|enter|tab|escape|none",
  "confidence": 0.0,
  "external_send": false,
  "reason": "raison courte"
}

Regles:
- x_ratio/y_ratio sont des ratios de l'ecran entre 0 et 1, pas des pixels.
- Si tu vois un bouton Envoyer/Send et que l'instruction demande d'envoyer, target="send_button" et external_send=true.
- Si l'instruction demande seulement de preparer/coller un brouillon, ne choisis pas Envoyer.
- Si tu n'es pas assez sur, action="none" avec confidence faible.
- Ne lis pas, ne repete pas et ne copie pas de secrets visibles.
""".strip()


def wants_visual_action(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    if re.search(r"\bx\s*[=:]?\s*\d{1,5}\D{1,20}\by\s*[=:]?\s*\d{1,5}\b", normalized):
        return False
    return any(
        marker in normalized
        for marker in (
            "clique sur",
            "click sur",
            "bouton",
            "champ visible",
            "champ de message",
            "zone de texte",
            "zone visible",
            "colle",
            "coller",
            "envoyer",
            "send",
            "appuie sur",
            "trouve le bouton",
            "regarde l'ecran et clique",
            "regarde mon ecran et clique",
        )
    )


def _extract_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?", "", clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r"```$", "", clean).strip()

    try:
        payload = json.loads(clean)
    except ValueError:
        match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if not match:
            raise VisualActionError("Le modele vision n'a pas renvoye de JSON exploitable.")
        try:
            payload = json.loads(match.group(0))
        except ValueError as exc:
            raise VisualActionError("Le JSON de l'action visuelle est invalide.") from exc

    if not isinstance(payload, dict):
        raise VisualActionError("Action visuelle inattendue.")
    return payload


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _looks_like_external_send(payload: dict[str, Any], instruction: str) -> bool:
    combined = " ".join(
        str(value).lower()
        for value in (
            payload.get("target", ""),
            payload.get("reason", ""),
            payload.get("action", ""),
            instruction,
        )
    )
    combined = " ".join(combined.split())

    if any(
        marker in combined
        for marker in (
            "send_button",
            "bouton envoyer",
            "bouton send",
            "publier",
            "publication",
            "post button",
            "reply button",
            "envoyer le message",
            "envoyer le mail",
            "envoyer l'email",
            "envoyer l email",
            "send message",
            "send email",
        )
    ):
        return True

    if any(marker in combined for marker in ("envoyer", "send")):
        safe_draft_markers = (
            "sans envoyer",
            "ne pas envoyer",
            "n'envoie pas",
            "ne l'envoie pas",
            "preparer",
            "préparer",
            "brouillon",
            "coller",
            "colle",
            "draft",
        )
        return not any(marker in combined for marker in safe_draft_markers)

    return False


def _execute_visual_payload(payload: dict[str, Any]) -> dict[str, object]:
    action = str(payload.get("action", "none")).strip().lower()
    confidence = _as_float(payload.get("confidence"), 0.0)
    external_send = bool(payload.get("external_send", False))

    if confidence < settings.eva_visual_action_min_confidence:
        return {
            "executed": False,
            "blocked": True,
            "reason": (
                f"Confiance trop faible ({round(confidence * 100)}%). "
                "Je n'ai pas clique pour eviter une mauvaise action."
            ),
        }

    if external_send and not settings.eva_allow_auto_external_send:
        return {
            "executed": False,
            "blocked": True,
            "reason": (
                "Le bouton detecte semble envoyer un message. "
                "EVA_ALLOW_AUTO_EXTERNAL_SEND=false, donc je ne clique pas sur Envoyer automatiquement."
            ),
        }

    try:
        if action == "click":
            x_ratio = payload.get("x_ratio")
            y_ratio = payload.get("y_ratio")
            if x_ratio is not None and y_ratio is not None:
                result = click_ratio(_as_float(x_ratio), _as_float(y_ratio))
            else:
                result = click_pixel(int(payload.get("x", 0)), int(payload.get("y", 0)))
            return {"executed": result.executed, "blocked": False, "reason": result.message}

        if action == "hotkey":
            hotkey = str(payload.get("hotkey", "none")).strip().lower()
            if hotkey == "ctrl+v":
                result = press_hotkey(("ctrl", "v"))
            elif hotkey in {"enter", "tab", "escape"}:
                result = press_key(hotkey)  # type: ignore[arg-type]
            else:
                return {
                    "executed": False,
                    "blocked": True,
                    "reason": f"Raccourci non supporte: {hotkey}.",
                }
            return {"executed": result.executed, "blocked": False, "reason": result.message}
    except (DesktopAutomationError, OSError, ValueError) as exc:
        raise VisualActionError(str(exc)) from exc

    return {"executed": False, "blocked": False, "reason": "Aucune action visuelle executee."}


async def analyze_visual_action(instruction: str, execute: bool = True) -> dict[str, object]:
    if not settings.eva_visual_action_enabled:
        raise VisualActionError("Actions visuelles desactivees. Active EVA_VISUAL_ACTION_ENABLED=true.")

    try:
        capture = capture_screen()
    except ScreenReaderError as exc:
        raise VisualActionError(str(exc)) from exc

    path = Path(str(capture["path"]))
    prompt = f"{VISUAL_ACTION_PROMPT}\n\nInstruction de Victor:\n{instruction.strip()}"

    try:
        raw = await ask_ollama_vision(
            image_base64=_encode_capture(path),
            prompt=prompt,
            model=settings.eva_screen_vision_model,
        )
    except (OllamaClientError, ScreenReaderError) as exc:
        raise VisualActionError(str(exc)) from exc

    payload = _extract_json(raw)
    payload["external_send"] = bool(payload.get("external_send", False)) or _looks_like_external_send(
        payload,
        instruction,
    )
    execution = _execute_visual_payload(payload) if execute else {
        "executed": False,
        "blocked": False,
        "reason": "Analyse seulement.",
    }

    return {
        "capture": capture,
        "vision_model": settings.eva_screen_vision_model,
        "decision": payload,
        "execution": execution,
    }


def format_visual_action_response(result: dict[str, object]) -> str:
    decision = result.get("decision", {})
    execution = result.get("execution", {})
    if not isinstance(decision, dict):
        decision = {}
    if not isinstance(execution, dict):
        execution = {}

    return (
        "Source: vision locale de l'ecran + hands desktop.\n"
        f"Cible interpretee: {decision.get('target', 'inconnue')}\n"
        f"Action proposee: {decision.get('action', 'none')}\n"
        f"Confiance: {round(_as_float(decision.get('confidence')) * 100)}%\n"
        f"Raison: {decision.get('reason', '')}\n\n"
        f"Execution: {execution.get('reason', '')}"
    ).strip()

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.config import settings
from app.integrations.browser import open_url
from app.integrations.browser_actions import detect_browser_open_url
from app.integrations.browser_assistant import detect_browser_assist
from app.integrations.desktop_automation import (
    DesktopAutomationError,
    click_ratio,
    paste_text,
    press_hotkey,
    press_key,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama_vision
from app.screen.screen_reader import ScreenReaderError, _encode_capture, capture_screen
from app.screen.visual_action import _looks_like_external_send


class ScreenNavigationError(Exception):
    """Raised when Eva cannot navigate the local screen safely."""


SCREEN_NAVIGATION_PROMPT = """
Tu es Eva Screen Navigator. Tu regardes l'ecran local du PC de Victor.

But: faire avancer la tache de Victor par UNE action UI concrete et verifiable.

Reponds uniquement en JSON valide, sans Markdown:
{
  "action": "click" | "hotkey" | "paste_text" | "open_url" | "wait" | "none",
  "target": "description courte du bouton/champ/page vise",
  "x_ratio": 0.0,
  "y_ratio": 0.0,
  "hotkey": "ctrl+v|ctrl+l|enter|tab|escape|none",
  "text": "texte a coller si action=paste_text",
  "url": "https://...",
  "confidence": 0.0,
  "done": false,
  "external_send": false,
  "reason": "raison courte"
}

Regles:
- Raisonne en interne: comprendre l'objectif, identifier l'app active, choisir le chemin le plus court, verifier le resultat attendu.
- Clique seulement si le bouton/champ cible est clairement visible.
- Si l'instruction demande d'ouvrir un site, une page ou une video et que l'URL est claire, action="open_url".
- Si l'instruction demande "ouvre X et clique/remplis", ouvre d'abord la destination puis utilise les captures suivantes pour agir.
- Si la tache est deja accomplie a l'ecran, action="none" et done=true.
- Si le bouton vise envoie, publie, repond ou paie, external_send=true.
- Ne choisis jamais un bouton Envoyer/Publier/Payer si Victor demande seulement de preparer ou brouillonner.
- Ne lis pas et ne repete pas les secrets visibles.
- Si tu n'es pas assez sur, action="none" avec confidence faible et explique la prochaine piste.
""".strip()


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def wants_screen_navigation(message: str) -> bool:
    normalized = _normalize(message)
    if re.search(r"\bx\s*[=:]?\s*\d{1,5}\D{1,20}\by\s*[=:]?\s*\d{1,5}\b", normalized):
        return False

    strong_markers = (
        "navigue sur mon ecran",
        "navigue dans l'ecran",
        "pilote mon ecran",
        "utilise mon ecran",
        "regarde l'ecran et",
        "regarde mon ecran et",
        "sur mon ecran",
        "a l'ecran",
        "dans la fenetre",
        "fenetre active",
        "pilote le pc",
        "pilote mon pc",
        "controle mon pc",
        "trouve le bouton",
        "clique sur le bon bouton",
        "remplis le champ",
        "remplis le formulaire",
        "selectionne le",
        "selectionne la",
    )
    if any(marker in normalized for marker in strong_markers):
        return True

    action_markers = (
        "clique",
        "click",
        "bouton",
        "champ",
        "colle",
        "coller",
        "remplis",
        "selectionne",
        "choisis",
        "appuie",
    )
    ui_context = (
        "brave",
        "navigateur",
        "linkedin",
        "gmail",
        "beeper",
        "spotify",
        "cursor",
        "youtube",
        "fenetre",
        "page",
        "onglet",
    )
    if any(marker in normalized for marker in action_markers) and any(
        marker in normalized for marker in ui_context
    ):
        return True

    return bool(
        re.search(
            r"\b(?:ouvre|ouvrir|lance|va sur)\b.{0,80}\b(?:clique|click|remplis|colle|selectionne|appuie)\b",
            normalized,
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
            raise ScreenNavigationError("Le modele vision n'a pas renvoye de JSON exploitable.")
        try:
            payload = json.loads(match.group(0))
        except ValueError as exc:
            raise ScreenNavigationError("Le JSON de navigation ecran est invalide.") from exc

    if not isinstance(payload, dict):
        raise ScreenNavigationError("Decision de navigation inattendue.")
    return payload


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ScreenNavigationError("URL refusee: Eva ouvre seulement des URLs http/https.")
    return url.strip()


def _detect_initial_url(message: str) -> str:
    assist = detect_browser_assist(message)
    if assist:
        return assist["url"]
    return detect_browser_open_url(message) or ""


def _safe_step_for_prompt(step: dict[str, object]) -> dict[str, object]:
    return {
        "index": step.get("index"),
        "action": step.get("action"),
        "target": step.get("target"),
        "confidence": step.get("confidence"),
        "executed": step.get("executed"),
        "blocked": step.get("blocked"),
        "done": step.get("done"),
        "message": step.get("message"),
        "reason": step.get("reason"),
    }


def _execute_payload(payload: dict[str, Any], instruction: str) -> dict[str, object]:
    action = str(payload.get("action", "none")).strip().lower()
    confidence = _as_float(payload.get("confidence"), 0.0)
    external_send = bool(payload.get("external_send", False)) or _looks_like_external_send(
        payload,
        instruction,
    )

    if action == "none":
        return {
            "executed": False,
            "blocked": False,
            "done": bool(payload.get("done", False)),
            "message": str(payload.get("reason", "Aucune action utile detectee.")),
        }

    if confidence < settings.eva_visual_action_min_confidence:
        return {
            "executed": False,
            "blocked": True,
            "done": False,
            "message": f"Confiance trop faible ({round(confidence * 100)}%). Action stoppee.",
        }

    if external_send and not settings.eva_allow_auto_external_send:
        return {
            "executed": False,
            "blocked": True,
            "done": False,
            "message": (
                "Action stoppee: le bouton detecte peut envoyer/publier. "
                "EVA_ALLOW_AUTO_EXTERNAL_SEND=false."
            ),
        }

    try:
        if action == "click":
            result = click_ratio(
                _as_float(payload.get("x_ratio")),
                _as_float(payload.get("y_ratio")),
            )
            return {"executed": result.executed, "blocked": False, "done": False, "message": result.message}

        if action == "hotkey":
            hotkey = str(payload.get("hotkey", "none")).strip().lower()
            if hotkey == "ctrl+v":
                result = press_hotkey(("ctrl", "v"))
            elif hotkey == "ctrl+l":
                result = press_hotkey(("ctrl", "l"))
            elif hotkey in {"enter", "tab", "escape"}:
                result = press_key(hotkey)  # type: ignore[arg-type]
            else:
                return {
                    "executed": False,
                    "blocked": True,
                    "done": False,
                    "message": f"Raccourci non supporte: {hotkey}.",
                }
            return {"executed": result.executed, "blocked": False, "done": False, "message": result.message}

        if action == "paste_text":
            text = str(payload.get("text", "")).strip()
            if not text:
                return {
                    "executed": False,
                    "blocked": True,
                    "done": False,
                    "message": "Texte vide: collage refuse.",
                }
            result = paste_text(text)
            return {"executed": result.executed, "blocked": False, "done": False, "message": result.message}

        if action == "open_url":
            url = _safe_url(str(payload.get("url", "")))
            open_url(url)
            return {
                "executed": True,
                "blocked": False,
                "done": False,
                "message": f"URL ouverte dans le navigateur local: {url}",
            }

        if action == "wait":
            time.sleep(1.0)
            return {"executed": True, "blocked": False, "done": False, "message": "Attente courte effectuee."}
    except (DesktopAutomationError, OSError, ValueError) as exc:
        raise ScreenNavigationError(str(exc)) from exc

    return {
        "executed": False,
        "blocked": True,
        "done": False,
        "message": f"Action non supportee: {action}.",
    }


async def navigate_screen(
    instruction: str,
    max_steps: int | None = None,
) -> dict[str, object]:
    if not settings.eva_screen_navigation_enabled:
        raise ScreenNavigationError("Navigation ecran desactivee. Active EVA_SCREEN_NAVIGATION_ENABLED=true.")
    if not settings.eva_visual_action_enabled:
        raise ScreenNavigationError("Actions visuelles desactivees. Active EVA_VISUAL_ACTION_ENABLED=true.")

    safe_steps = max(1, min(max_steps or settings.eva_screen_navigation_max_steps, 8))
    steps: list[dict[str, object]] = []

    initial_url = _detect_initial_url(instruction)
    if initial_url:
        url = _safe_url(initial_url)
        open_url(url)
        steps.append(
            {
                "index": 0,
                "action": "open_url",
                "target": url,
                "confidence": 1.0,
                "executed": True,
                "blocked": False,
                "done": False,
                "message": f"Destination initiale ouverte: {url}",
            }
        )
        time.sleep(1.2)

    for index in range(1, safe_steps + 1):
        try:
            capture = capture_screen()
        except ScreenReaderError as exc:
            if steps:
                steps.append(
                    {
                        "index": index,
                        "action": "none",
                        "target": "capture",
                        "confidence": 0.0,
                        "executed": False,
                        "blocked": True,
                        "done": False,
                        "message": f"Capture impossible apres action precedente: {exc}",
                    }
                )
                break
            raise ScreenNavigationError(str(exc)) from exc

        path = Path(str(capture["path"]))
        prompt = (
            f"{SCREEN_NAVIGATION_PROMPT}\n\n"
            f"Instruction de Victor:\n{instruction.strip()}\n\n"
            f"Etapes deja executees:\n"
            f"{json.dumps([_safe_step_for_prompt(step) for step in steps[-5:]], ensure_ascii=False)}"
        )

        try:
            raw = await ask_ollama_vision(
                image_base64=_encode_capture(path),
                prompt=prompt,
                model=settings.eva_screen_vision_model,
            )
        except OllamaClientError as exc:
            if steps:
                steps.append(
                    {
                        "index": index,
                        "capture": capture,
                        "action": "none",
                        "target": "vision",
                        "confidence": 0.0,
                        "executed": False,
                        "blocked": True,
                        "done": False,
                        "message": f"Vision Ollama indisponible apres action precedente: {exc}",
                    }
                )
                break
            raise ScreenNavigationError(str(exc)) from exc

        decision = _extract_json(raw)
        execution = _execute_payload(decision, instruction)
        step = {
            "index": index,
            "capture": capture,
            "action": decision.get("action", "none"),
            "target": decision.get("target", ""),
            "confidence": _as_float(decision.get("confidence")),
            "reason": decision.get("reason", ""),
            "executed": execution.get("executed", False),
            "blocked": execution.get("blocked", False),
            "done": execution.get("done", False) or bool(decision.get("done", False)),
            "message": execution.get("message", ""),
        }
        steps.append(step)

        if step["done"] or step["blocked"] or decision.get("action") == "none":
            break
        time.sleep(0.65)

    executed = [step for step in steps if step.get("executed")]
    blocked = [step for step in steps if step.get("blocked")]
    done = bool(steps and steps[-1].get("done"))

    return {
        "instruction": instruction,
        "vision_model": settings.eva_screen_vision_model,
        "steps": steps,
        "executed_count": len(executed),
        "blocked": bool(blocked),
        "done": done,
        "status": "blocked" if blocked else ("done" if done else ("partial" if executed else "no_action")),
        "next_hint": (
            "relancer avec /pilot en gardant la fenetre visible"
            if blocked
            else ("continuer la navigation ecran" if executed and not done else "")
        ),
    }


def format_screen_navigation_response(result: dict[str, object]) -> str:
    steps = result.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    lines = [
        "Source: navigation ecran locale + vision Ollama.",
        f"Statut: {result.get('status', 'inconnu')}",
        f"Modele vision: {result.get('vision_model', settings.eva_screen_vision_model)}",
        "",
        "Etapes:",
    ]
    for step in steps:
        if not isinstance(step, dict):
            continue
        confidence = round(_as_float(step.get("confidence")) * 100)
        status = "bloquee" if step.get("blocked") else ("executee" if step.get("executed") else "observee")
        lines.append(
            f"- {step.get('index')}. {step.get('action')} -> {step.get('target') or 'cible inconnue'} "
            f"({confidence}%, {status})"
        )
        detail = str(step.get("message") or step.get("reason") or "").strip()
        if detail:
            lines.append(f"  {detail}")

    if not steps:
        lines.append("- Aucune etape executee.")

    if result.get("blocked"):
        lines.append("")
        lines.append("Navigation stoppee avant action risquee ou incertaine.")
        next_hint = str(result.get("next_hint", "")).strip()
        if next_hint:
            lines.append(f"Prochaine piste: {next_hint}.")

    return "\n".join(lines).strip()

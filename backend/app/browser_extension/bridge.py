from __future__ import annotations

import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.screen.training_autopilot import (
    looks_like_blocked_assessment_request,
    wants_training_autopilot,
)


class BrowserExtensionError(Exception):
    """Raised when Eva cannot use the local browser extension bridge."""


BROWSER_EXTENSION_SYSTEM_PROMPT = """
Tu es Eva Browser Operator. Tu pilotes uniquement la page Brave visible via une extension locale.

Objectif: faire avancer une tache navigateur non critique, surtout un entrainement non officiel.

Retourne uniquement un JSON valide:
{
  "action": "click" | "set_value" | "focus" | "key" | "scroll" | "wait" | "none",
  "element_index": 0,
  "selector": "",
  "text": "",
  "key": "Enter|Tab|Escape",
  "direction": "down|up",
  "confidence": 0.0,
  "done": false,
  "blocked": false,
  "official_assessment": false,
  "reason": "raison courte",
  "learning_note": "ce qu'il faut retenir, sans secret"
}

Regles:
- Lis d'abord le texte visible et les elements interactifs.
- Pour un entrainement, choisis l'option la plus probable, clique, puis laisse la boucle verifier.
- Si tu vois examen officiel, certification, evaluation notee ou controle final: blocked=true, official_assessment=true, action="none".
- Ne clique pas sur payer, acheter, supprimer, publier, envoyer un mail/message ou confirmer une action de compte.
- Ne repete jamais un token, mot de passe ou secret.
- Si la tache est deja terminee, done=true et action="none".
""".strip()


ASSESSMENT_COACH_SYSTEM_PROMPT = """
Tu es Eva Study Coach. Tu aides Victor a s'entrainer sans prendre le controle d'un test note.

Retourne uniquement un JSON valide:
{
  "question": "question visible",
  "choices": ["choix A", "choix B"],
  "hint": "indice utile sans blabla",
  "reasoning": "raisonnement court pour apprendre",
  "likely_answer": "choix le plus probable si c'est une annale/mock/entrainement, sinon vide",
  "confidence": 0.0,
  "warning": "limite ou prudence"
}

Regles:
- N'explique pas comment automatiser ou soumettre le test.
- Ne propose pas de cliquer a la place de Victor.
- Si la page ressemble a une certification/examen officiel/evaluation finale, donne seulement un indice et un rappel de cours.
- Si la page indique annale, mock, entrainement ou sample, tu peux indiquer le choix le plus probable avec justification.
- Si tu n'es pas sur, laisse likely_answer vide et explique ce qu'il faut verifier.
""".strip()


DANGEROUS_ELEMENT_MARKERS = (
    "payer",
    "payment",
    "checkout",
    "acheter",
    "buy",
    "delete",
    "supprimer",
    "publier",
    "publish",
    "send email",
    "send message",
    "envoyer le mail",
    "envoyer le message",
    "logout",
    "deconnexion",
)

TRAINING_CONTEXT_MARKERS = (
    "entrainement",
    "exercice",
    "exercices",
    "practice",
    "training",
    "quiz",
    "qcm",
    "projet voltaire",
)


@dataclass
class BrowserAction:
    id: str
    tab_id: str
    payload: dict[str, Any]
    created_at: float = field(default_factory=time.time)


_latest_snapshots: dict[str, dict[str, Any]] = {}
_pending_actions: dict[str, BrowserAction] = {}
_action_results: dict[str, dict[str, Any]] = {}
_state_lock = asyncio.Lock()


def _now() -> float:
    return time.time()


def _clean_text(value: object, limit: int = 800) -> str:
    return " ".join(str(value or "").split())[:limit]


def _tab_id_from_snapshot(snapshot: dict[str, Any]) -> str:
    tab_id = str(snapshot.get("tab_id") or "").strip()
    if tab_id:
        return tab_id[:240]
    url = str(snapshot.get("tab_url") or snapshot.get("url") or "").strip()
    return url[:240] or "active"


def _snapshot_age(snapshot: dict[str, Any] | None) -> float | None:
    if not snapshot:
        return None
    observed = snapshot.get("_observed_at")
    if not isinstance(observed, (int, float)):
        return None
    return max(0.0, _now() - float(observed))


def _fresh_snapshot(max_age_seconds: float = 8.0) -> tuple[str, dict[str, Any]] | None:
    candidates = sorted(
        _latest_snapshots.items(),
        key=lambda item: float(item[1].get("_observed_at", 0.0)),
        reverse=True,
    )
    for tab_id, snapshot in candidates:
        age = _snapshot_age(snapshot)
        if age is not None and age <= max_age_seconds:
            return tab_id, snapshot
    return None


def is_browser_extension_ready(max_age_seconds: float = 8.0) -> bool:
    return _fresh_snapshot(max_age_seconds=max_age_seconds) is not None


def wants_browser_extension_training(message: str) -> bool:
    normalized = " ".join(message.lower().split())
    if "extension" in normalized and any(marker in normalized for marker in ("brave", "navigateur", "browser")):
        return True
    if "dans brave" in normalized and wants_training_autopilot(message):
        return True
    if "sur brave" in normalized and wants_training_autopilot(message):
        return True
    return wants_training_autopilot(message) and any(
        marker in normalized for marker in ("page", "site", "navigateur", "brave", "chrome")
    )


async def record_snapshot(snapshot: dict[str, Any]) -> dict[str, object]:
    tab_id = _tab_id_from_snapshot(snapshot)
    safe_snapshot = dict(snapshot)
    safe_snapshot["tab_id"] = tab_id
    safe_snapshot["_observed_at"] = _now()
    async with _state_lock:
        _latest_snapshots[tab_id] = safe_snapshot
    return {"ok": True, "tab_id": tab_id}


async def next_action(tab_id: str) -> dict[str, object]:
    clean_tab_id = tab_id.strip()[:240] or "active"
    async with _state_lock:
        action = _pending_actions.pop(clean_tab_id, None)
    if not action:
        return {"action": None}
    return {"action": action.payload}


async def record_action_result(result: dict[str, Any]) -> dict[str, object]:
    action_id = str(result.get("action_id") or "").strip()
    if not action_id:
        raise BrowserExtensionError("action_id manquant.")
    payload = dict(result)
    payload["_received_at"] = _now()
    async with _state_lock:
        _action_results[action_id] = payload
    return {"ok": True}


def browser_extension_status() -> dict[str, object]:
    fresh = _fresh_snapshot(max_age_seconds=8.0)
    latest_age = None
    latest = None
    if fresh:
        tab_id, snapshot = fresh
        latest_age = _snapshot_age(snapshot)
        latest = {
            "tab_id": tab_id,
            "url": snapshot.get("tab_url", ""),
            "title": snapshot.get("title", ""),
            "elements": len(snapshot.get("elements", []) or []),
        }
    return {
        "enabled": True,
        "connected": fresh is not None,
        "latest_age_seconds": latest_age,
        "latest": latest,
        "snapshots": len(_latest_snapshots),
        "pending_actions": len(_pending_actions),
        "local_only": True,
    }


def _elements_for_prompt(snapshot: dict[str, Any]) -> list[dict[str, object]]:
    raw_elements = snapshot.get("elements")
    if not isinstance(raw_elements, list):
        return []
    elements: list[dict[str, object]] = []
    for item in raw_elements[:80]:
        if not isinstance(item, dict):
            continue
        elements.append(
            {
                "index": item.get("index"),
                "tag": item.get("tag", ""),
                "role": item.get("role", ""),
                "type": item.get("type", ""),
                "label": _clean_text(item.get("label", ""), 220),
                "text": _clean_text(item.get("text", ""), 220),
                "aria": _clean_text(item.get("aria", ""), 120),
                "placeholder": _clean_text(item.get("placeholder", ""), 120),
                "selector": _clean_text(item.get("selector", ""), 240),
            }
        )
    return elements


def _training_context(instruction: str, snapshot: dict[str, Any]) -> str:
    return (
        f"Instruction de Victor:\n{instruction.strip()}\n\n"
        f"Page:\n- titre: {_clean_text(snapshot.get('title'), 180)}\n"
        f"- url: {_clean_text(snapshot.get('tab_url'), 260)}\n"
        f"- viewport: {snapshot.get('viewport', {})}\n\n"
        f"Texte visible:\n{_clean_text(snapshot.get('visible_text'), 2600)}\n\n"
        "Elements interactifs visibles:\n"
        f"{_elements_for_prompt(snapshot)}"
    )


def _assessment_coach_context(instruction: str, snapshot: dict[str, Any]) -> str:
    return (
        f"Instruction de Victor:\n{instruction.strip()}\n\n"
        f"Page:\n- titre: {_clean_text(snapshot.get('title'), 180)}\n"
        f"- url: {_clean_text(snapshot.get('tab_url'), 260)}\n\n"
        f"Texte visible:\n{_clean_text(snapshot.get('visible_text'), 3200)}\n\n"
        "Elements interactifs visibles:\n"
        f"{_elements_for_prompt(snapshot)}"
    )


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _safe_index(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _selected_element_text(action: dict[str, Any], snapshot: dict[str, Any]) -> str:
    index = _safe_index(action.get("element_index"))
    for element in _elements_for_prompt(snapshot):
        if _safe_index(element.get("index")) == index:
            return " ".join(
                str(element.get(key, ""))
                for key in ("tag", "role", "type", "label", "text", "aria", "placeholder")
            ).lower()
    return str(action.get("selector", "")).lower()


def _looks_like_assessment_page(snapshot: dict[str, Any]) -> bool:
    url = str(snapshot.get("tab_url") or snapshot.get("url") or "").lower()
    title = str(snapshot.get("title") or "").lower()
    text = str(snapshot.get("visible_text") or "").lower()
    page_text = f"{title} {text}"

    if any(marker in page_text for marker in ("certification", "examen officiel", "evaluation notee", "controle final")):
        return True
    if "noté sur" in page_text or "note sur" in page_text:
        return True
    if "terminer le test" in page_text or "navigation du test" in page_text:
        return True
    if ("exam" in title or "examen" in title) and "test" in title:
        return True
    if ("/mod/quiz/attempt" in url or "attempt.php" in url) and any(
        marker in page_text for marker in ("test", "noté", "note", "question", "terminer")
    ):
        return True
    return False


def _safe_action_payload(action: dict[str, Any], snapshot: dict[str, Any], instruction: str) -> dict[str, Any]:
    payload = dict(action)
    name = str(payload.get("action", "none")).strip().lower()
    if name not in {"click", "set_value", "focus", "key", "scroll", "wait", "none"}:
        name = "none"
    payload["action"] = name
    payload["id"] = str(payload.get("id") or uuid.uuid4())
    payload["element_index"] = _safe_index(payload.get("element_index"))
    payload["confidence"] = _as_float(payload.get("confidence"), 0.0)
    payload["selector"] = _clean_text(payload.get("selector"), 260)
    payload["text"] = str(payload.get("text") or "")[:1200]
    payload["key"] = _clean_text(payload.get("key") or "Enter", 20)
    payload["direction"] = "up" if str(payload.get("direction", "")).lower() == "up" else "down"

    element_text = _selected_element_text(payload, snapshot)
    if any(marker in element_text for marker in DANGEROUS_ELEMENT_MARKERS):
        payload["action"] = "none"
        payload["blocked"] = True
        payload["reason"] = "Action navigateur stoppee: element potentiellement critique."

    page_text = f"{snapshot.get('title', '')} {snapshot.get('visible_text', '')}".lower()
    if bool(payload.get("official_assessment")) or looks_like_blocked_assessment_request(instruction):
        payload["action"] = "none"
        payload["blocked"] = True
        payload["official_assessment"] = True
        payload["reason"] = "Stop: examen/certification/evaluation officielle detectee."
    elif _looks_like_assessment_page(snapshot):
        payload["action"] = "none"
        payload["blocked"] = True
        payload["official_assessment"] = True
        payload["reason"] = (
            "Stop: page de test/evaluation detectee. Eva peut aider a reviser ou expliquer, "
            "mais ne repond pas automatiquement a un test note."
        )

    if payload["action"] not in {"none", "wait"} and payload["confidence"] < 0.58:
        payload["action"] = "none"
        payload["blocked"] = True
        payload["reason"] = f"Confiance trop faible ({round(payload['confidence'] * 100)}%)."

    if payload["action"] == "none" and not payload.get("done") and not payload.get("blocked") and not payload.get("reason"):
        payload["reason"] = (
            "Aucune action fiable choisie par le modele. Eva a observe la page, mais n'a pas trouve "
            "un clic/remplissage suffisamment clair."
        )

    return payload


async def _build_assessment_coach(snapshot: dict[str, Any], instruction: str) -> dict[str, object]:
    try:
        payload = await ask_ollama_json(
            ASSESSMENT_COACH_SYSTEM_PROMPT,
            _assessment_coach_context(instruction, snapshot),
            model=settings.ollama_reasoning_model,
            timeout_seconds=settings.eva_browser_extension_reasoning_timeout_seconds,
            temperature=0.05,
        )
    except OllamaClientError as exc:
        return {
            "question": "",
            "choices": [],
            "hint": "La page est lisible, mais Ollama n'a pas produit d'aide fiable assez vite.",
            "reasoning": str(exc),
            "likely_answer": "",
            "confidence": 0.0,
            "warning": "Aucune action n'a ete executee.",
        }

    choices = payload.get("choices")
    if not isinstance(choices, list):
        choices = []

    return {
        "question": _clean_text(payload.get("question"), 500),
        "choices": [_clean_text(choice, 240) for choice in choices[:8]],
        "hint": _clean_text(payload.get("hint"), 500),
        "reasoning": _clean_text(payload.get("reasoning"), 900),
        "likely_answer": _clean_text(payload.get("likely_answer"), 500),
        "confidence": _as_float(payload.get("confidence"), 0.0),
        "warning": _clean_text(payload.get("warning"), 500) or "Aucune action n'a ete executee.",
    }


async def _queue_action(tab_id: str, action: dict[str, Any]) -> None:
    browser_action = BrowserAction(id=str(action["id"]), tab_id=tab_id, payload=action)
    async with _state_lock:
        _pending_actions[tab_id] = browser_action


async def _wait_for_result(action_id: str, timeout_seconds: float = 8.0) -> dict[str, Any] | None:
    deadline = _now() + timeout_seconds
    while _now() < deadline:
        async with _state_lock:
            result = _action_results.pop(action_id, None)
        if result:
            return result
        await asyncio.sleep(0.25)
    return None


async def run_browser_training(
    instruction: str,
    max_rounds: int = 14,
) -> dict[str, object]:
    safe_rounds = max(1, min(int(max_rounds), 40))
    steps: list[dict[str, object]] = []
    study_help: dict[str, object] | None = None
    blocked_by_instruction = looks_like_blocked_assessment_request(instruction)

    for round_index in range(1, safe_rounds + 1):
        fresh = _fresh_snapshot(max_age_seconds=10.0)
        if not fresh:
            raise BrowserExtensionError(
                "Extension Brave non connectee ou aucune page active observee. "
                "Installe/active Eva Browser Bridge puis recharge la page."
            )
        tab_id, snapshot = fresh

        if blocked_by_instruction:
            action = {
                "action": "none",
                "confidence": 0.0,
                "blocked": True,
                "official_assessment": True,
                "reason": "Instruction de reponse automatique a une evaluation detectee.",
            }
        else:
            try:
                action = await ask_ollama_json(
                    BROWSER_EXTENSION_SYSTEM_PROMPT,
                    _training_context(instruction, snapshot),
                    model=settings.ollama_reasoning_model,
                    timeout_seconds=settings.eva_browser_extension_reasoning_timeout_seconds,
                    temperature=0.05,
                )
            except OllamaClientError as exc:
                message = str(exc)
                if "ne repond pas assez vite" in message:
                    message = (
                        "Ollama a mis trop longtemps a choisir l'action navigateur. "
                        "C'est souvent le premier chargement du modele ou un modele trop lourd. "
                        "Reessaie une fois, ou augmente EVA_BROWSER_EXTENSION_REASONING_TIMEOUT_SECONDS."
                    )
                raise BrowserExtensionError(message) from exc

        payload = _safe_action_payload(action, snapshot, instruction)
        blocked = bool(payload.get("blocked"))
        done = bool(payload.get("done"))
        executed = False
        result_message = ""

        if blocked and payload.get("official_assessment"):
            study_help = await _build_assessment_coach(snapshot, instruction)

        if not blocked and not done and payload["action"] != "none":
            await _queue_action(tab_id, payload)
            result = await _wait_for_result(str(payload["id"]))
            if result:
                executed = bool(result.get("ok"))
                result_message = _clean_text(result.get("message"), 260)
            else:
                blocked = True
                result_message = "L'extension n'a pas renvoye le resultat de l'action."
            await asyncio.sleep(0.8)

        steps.append(
            {
                "index": round_index,
                "url": snapshot.get("tab_url", ""),
                "title": snapshot.get("title", ""),
                "action": payload.get("action", "none"),
                "target": payload.get("selector") or payload.get("element_index"),
                "confidence": payload.get("confidence", 0.0),
                "executed": executed,
                "blocked": blocked,
                "done": done,
                "reason": payload.get("reason", ""),
                "learning_note": payload.get("learning_note", ""),
                "result": result_message,
            }
        )

        if blocked or done or payload["action"] == "none":
            break

    executed_count = sum(1 for step in steps if step.get("executed"))
    blocked = bool(steps and steps[-1].get("blocked"))
    done = bool(steps and steps[-1].get("done"))
    status = "blocked" if blocked else ("done" if done else ("partial" if executed_count else "no_action"))
    return {
        "status": status,
        "blocked": blocked,
        "done": done,
        "executed_count": executed_count,
        "rounds_used": len(steps),
        "max_rounds": safe_rounds,
        "steps": steps,
        "reason": str(steps[-1].get("reason", "")) if steps else "",
        "study_help": study_help or {},
        "source": "Eva Browser Bridge",
    }


def format_browser_training_response(result: dict[str, object]) -> str:
    steps = result.get("steps")
    if not isinstance(steps, list):
        steps = []

    lines = [
        "Mode navigateur Brave via extension Eva.",
        f"Statut: {result.get('status', 'inconnu')}",
        f"Tours: {result.get('rounds_used', len(steps))}/{result.get('max_rounds', '?')}",
        f"Actions executees: {result.get('executed_count', 0)}",
    ]
    reason = _clean_text(result.get("reason"), 260)
    if reason:
        lines.append(f"Note: {reason}")
    study_help = result.get("study_help")
    if isinstance(study_help, dict) and any(study_help.get(key) for key in ("question", "hint", "reasoning", "likely_answer")):
        lines.append("")
        lines.append("Mode coach:")
        question = _clean_text(study_help.get("question"), 500)
        if question:
            lines.append(f"Question: {question}")
        choices = study_help.get("choices")
        if isinstance(choices, list) and choices:
            lines.append("Choix visibles:")
            for choice in choices[:6]:
                lines.append(f"- {_clean_text(choice, 220)}")
        hint = _clean_text(study_help.get("hint"), 500)
        if hint:
            lines.append(f"Indice: {hint}")
        likely = _clean_text(study_help.get("likely_answer"), 500)
        if likely:
            confidence = round(_as_float(study_help.get("confidence")) * 100)
            lines.append(f"Piste probable: {likely} ({confidence}%)")
        reasoning = _clean_text(study_help.get("reasoning"), 900)
        if reasoning:
            lines.append(f"Pourquoi: {reasoning}")
        warning = _clean_text(study_help.get("warning"), 500)
        if warning:
            lines.append(f"Limite: {warning}")
    if steps:
        lines.append("")
        lines.append("Dernieres actions:")
    for step in steps[-8:]:
        if not isinstance(step, dict):
            continue
        confidence = round(_as_float(step.get("confidence")) * 100)
        status = "bloquee" if step.get("blocked") else ("faite" if step.get("executed") else "observee")
        lines.append(
            f"- {step.get('index')}. {step.get('action')} -> {step.get('target')} ({confidence}%, {status})"
        )
        note = _clean_text(step.get("learning_note") or step.get("result") or step.get("reason"), 220)
        if note:
            lines.append(f"  {note}")
    return "\n".join(lines).strip()

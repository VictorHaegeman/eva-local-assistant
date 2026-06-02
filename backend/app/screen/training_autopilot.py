import json
import re
import time
from pathlib import Path
from typing import Any

from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama_vision
from app.screen.screen_navigator import (
    ScreenNavigationError,
    _as_float,
    _execute_payload,
    _extract_json,
    _safe_step_for_prompt,
)
from app.screen.screen_reader import ScreenReaderError, _encode_capture, capture_screen


class ScreenTrainingError(Exception):
    """Raised when Eva cannot run a local visual training autopilot."""


TRAINING_AUTOPILOT_PROMPT = """
Tu es Eva Training Operator. Tu pilotes l'ecran local du PC de Victor pour un exercice d'entrainement non officiel.

But: continuer l'exercice jusqu'a une fin visible, un blocage reel, ou la limite de tours.

Reponds uniquement en JSON valide, sans Markdown:
{
  "action": "click" | "hotkey" | "paste_text" | "wait" | "none",
  "target": "description courte du bouton/champ/reponse vise",
  "x_ratio": 0.0,
  "y_ratio": 0.0,
  "hotkey": "ctrl+v|enter|tab|escape|none",
  "text": "texte a coller si action=paste_text",
  "confidence": 0.0,
  "done": false,
  "blocked": false,
  "official_assessment": false,
  "learning_note": "regle ou observation utile, sans secret",
  "reason": "raison courte"
}

Regles:
- Raisonne en interne avant de cliquer: lis la consigne visible, repere les choix, estime la meilleure action.
- Si c'est un entrainement visible ou une page de pratique, tu peux choisir une reponse et cliquer.
- Si la page ressemble a un examen officiel, une certification, une evaluation notee ou un controle final, mets official_assessment=true, action="none", blocked=true.
- Si tu ne vois pas assez pour decider, action="wait" ou action="none" avec blocked=true.
- Ne clique jamais sur paiement, achat, publication, envoyer un mail/message, suppression, ou validation critique hors exercice.
- Si l'exercice est termine, action="none", done=true.
- Ne lis pas et ne repete pas les secrets visibles.
""".strip()


TRAINING_MARKERS = (
    "exercice",
    "exercices",
    "exo",
    "exos",
    "entrainement",
    "entrainements",
    "training",
    "practice",
    "projet voltaire",
    "voltaire",
    "quiz",
    "qcm",
    "clique les reponses",
    "fais l'exercice",
    "fais les exercices",
    "continue l'exercice",
)

OFFICIAL_ASSESSMENT_MARKERS = (
    "examen officiel",
    "certification",
    "controle note",
    "controle note",
    "evaluation officielle",
    "evaluation notee",
    "test officiel",
    "devoir note",
    "partiel",
    "concours",
)

TRAINING_ALLOW_MARKERS = (
    "entrainement",
    "non officiel",
    "pas officiel",
    "practice",
    "training",
    "exercice libre",
)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def wants_training_autopilot(message: str) -> bool:
    normalized = _normalize(message)
    if any(marker in normalized for marker in TRAINING_MARKERS):
        return True
    return bool(
        re.search(
            r"\b(?:fais|continue|termine|resous|reponds?)\b.{0,80}\b(?:qcm|quiz|exercice|exo)\b",
            normalized,
        )
    )


def looks_like_blocked_assessment_request(message: str) -> bool:
    normalized = _normalize(message)
    if any(marker in normalized for marker in TRAINING_ALLOW_MARKERS):
        return False
    return any(marker in normalized for marker in OFFICIAL_ASSESSMENT_MARKERS)


def _format_round_prompt(instruction: str, steps: list[dict[str, object]]) -> str:
    return (
        f"{TRAINING_AUTOPILOT_PROMPT}\n\n"
        f"Instruction de Victor:\n{instruction.strip()}\n\n"
        "Historique recent des actions:\n"
        f"{json.dumps([_safe_step_for_prompt(step) for step in steps[-8:]], ensure_ascii=False)}"
    )


def _safe_training_payload(payload: dict[str, Any], instruction: str) -> dict[str, Any]:
    payload = dict(payload)
    action = str(payload.get("action", "none")).strip().lower()
    if action == "open_url":
        payload["action"] = "none"
        payload["blocked"] = True
        payload["reason"] = "open_url refuse dans le mode entrainement: la page doit deja etre visible."
    if bool(payload.get("official_assessment", False)) or looks_like_blocked_assessment_request(instruction):
        payload["action"] = "none"
        payload["blocked"] = True
        payload["done"] = False
        payload["reason"] = (
            "Stop: la demande ou l'ecran ressemble a une evaluation officielle/notee. "
            "Mode entrainement uniquement."
        )
    return payload


async def run_training_autopilot(
    instruction: str,
    max_rounds: int | None = None,
) -> dict[str, object]:
    if not settings.eva_screen_training_enabled:
        raise ScreenTrainingError("Autopilote entrainement desactive. Active EVA_SCREEN_TRAINING_ENABLED=true.")
    if not settings.eva_screen_enabled or not settings.eva_visual_action_enabled:
        raise ScreenTrainingError("Lecture ecran/actions visuelles desactivees.")

    safe_rounds = max(1, min(max_rounds or settings.eva_screen_training_max_rounds, 40))
    steps: list[dict[str, object]] = []
    no_progress_rounds = 0

    if looks_like_blocked_assessment_request(instruction):
        return {
            "instruction": instruction,
            "vision_model": settings.eva_screen_vision_model,
            "steps": [],
            "status": "blocked",
            "blocked": True,
            "done": False,
            "executed_count": 0,
            "reason": "Mode refuse pour examen/certification/evaluation officielle. Mode entrainement uniquement.",
        }

    for index in range(1, safe_rounds + 1):
        try:
            capture = capture_screen()
        except ScreenReaderError as exc:
            raise ScreenTrainingError(str(exc)) from exc

        path = Path(str(capture["path"]))
        prompt = _format_round_prompt(instruction, steps)

        try:
            raw = await ask_ollama_vision(
                image_base64=_encode_capture(path),
                prompt=prompt,
                model=settings.eva_screen_vision_model,
            )
        except OllamaClientError as exc:
            raise ScreenTrainingError(str(exc)) from exc

        try:
            decision = _safe_training_payload(_extract_json(raw), instruction)
            execution = _execute_payload(decision, instruction)
        except ScreenNavigationError as exc:
            raise ScreenTrainingError(str(exc)) from exc
        blocked = bool(decision.get("blocked", False)) or bool(execution.get("blocked", False))
        done = bool(decision.get("done", False)) or bool(execution.get("done", False))
        executed = bool(execution.get("executed", False))

        step = {
            "index": index,
            "capture": capture,
            "action": decision.get("action", "none"),
            "target": decision.get("target", ""),
            "confidence": _as_float(decision.get("confidence")),
            "executed": executed,
            "blocked": blocked,
            "done": done,
            "official_assessment": bool(decision.get("official_assessment", False)),
            "learning_note": str(decision.get("learning_note", "")).strip(),
            "reason": str(decision.get("reason", "")).strip(),
            "message": execution.get("message", ""),
        }
        steps.append(step)

        if done or blocked:
            break
        if executed:
            no_progress_rounds = 0
        else:
            no_progress_rounds += 1
            if no_progress_rounds >= 2:
                break
        time.sleep(0.8)

    executed_count = sum(1 for step in steps if step.get("executed"))
    blocked = bool(steps and steps[-1].get("blocked"))
    done = bool(steps and steps[-1].get("done"))
    status = "blocked" if blocked else ("done" if done else ("partial" if executed_count else "no_action"))

    return {
        "instruction": instruction,
        "vision_model": settings.eva_screen_vision_model,
        "steps": steps,
        "status": status,
        "blocked": blocked,
        "done": done,
        "executed_count": executed_count,
        "rounds_used": len(steps),
        "max_rounds": safe_rounds,
        "reason": str(steps[-1].get("reason", "")) if steps else "",
    }


def format_training_autopilot_response(result: dict[str, object]) -> str:
    steps = result.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    lines = [
        "Mode entrainement ecran.",
        f"Statut: {result.get('status', 'inconnu')}",
        f"Modele vision: {result.get('vision_model', settings.eva_screen_vision_model)}",
        f"Tours: {result.get('rounds_used', len(steps))}/{result.get('max_rounds', '?')}",
        f"Actions executees: {result.get('executed_count', 0)}",
    ]

    reason = str(result.get("reason", "")).strip()
    if reason:
        lines.append(f"Note: {reason}")

    if steps:
        lines.append("")
        lines.append("Dernieres etapes:")
    for step in steps[-8:]:
        if not isinstance(step, dict):
            continue
        confidence = round(_as_float(step.get("confidence")) * 100)
        status = "bloquee" if step.get("blocked") else ("faite" if step.get("executed") else "observee")
        lines.append(
            f"- {step.get('index')}. {step.get('action')} -> {step.get('target') or 'cible inconnue'} "
            f"({confidence}%, {status})"
        )
        note = str(step.get("learning_note") or step.get("message") or "").strip()
        if note:
            lines.append(f"  {note[:240]}")

    if result.get("blocked"):
        lines.append("")
        lines.append("Arret: blocage detecte ou action trop risquee/incertaine.")
    elif not result.get("done"):
        lines.append("")
        lines.append("Limite atteinte ou progression incertaine: relance /training si tu veux continuer sur la page visible.")

    return "\n".join(lines).strip()

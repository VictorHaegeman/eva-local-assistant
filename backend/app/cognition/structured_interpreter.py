from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, cast

from app.agents.action_planner import PlanRoute, build_action_plan_for_route
from app.agents.intent_router import has_news_context
from app.agents.understanding import (
    ExpectedOutcome,
    PrimaryDomain,
    SafetyLevel,
    UnderstandingFrame,
    _required_evidence,
    _safety_level,
    _tool_preference,
)
from app.config import settings
from app.llm.ollama_client import OllamaClientError, ask_ollama_json


ALLOWED_ROUTES: tuple[str, ...] = (
    "terminal_error",
    "screen_read",
    "google_oauth_setup",
    "calendar_read",
    "gmail_read",
    "gmail_reply_audit",
    "gmail_reply_draft",
    "project_factory",
    "cursor_work",
    "local_status",
    "browser_or_video",
    "spotify",
    "desktop_control",
    "beeper_messages",
    "linkedin_activity",
    "linkedin_browser_post",
    "web_search",
    "generic_chat",
)

ALLOWED_DOMAINS: tuple[str, ...] = (
    "gmail",
    "calendar",
    "google_setup",
    "screen",
    "terminal",
    "project",
    "cursor",
    "browser",
    "spotify",
    "desktop",
    "beeper",
    "linkedin",
    "design",
    "web",
    "memory",
    "status",
    "chat",
)

ALLOWED_OUTCOMES: tuple[str, ...] = (
    "answer",
    "read",
    "read_then_summarize",
    "read_then_audit",
    "read_then_open",
    "draft",
    "open",
    "execute_local",
    "diagnose",
    "create_workspace",
    "prepare_prompt",
    "search",
    "clarify",
)

ROUTE_DEFAULTS: dict[str, tuple[str, str]] = {
    "terminal_error": ("terminal", "diagnose"),
    "screen_read": ("screen", "execute_local"),
    "google_oauth_setup": ("google_setup", "execute_local"),
    "calendar_read": ("calendar", "read_then_summarize"),
    "gmail_read": ("gmail", "read_then_summarize"),
    "gmail_reply_audit": ("gmail", "read_then_audit"),
    "gmail_reply_draft": ("gmail", "draft"),
    "project_factory": ("project", "create_workspace"),
    "cursor_work": ("cursor", "prepare_prompt"),
    "local_status": ("status", "read"),
    "browser_or_video": ("browser", "open"),
    "spotify": ("spotify", "open"),
    "desktop_control": ("desktop", "execute_local"),
    "beeper_messages": ("beeper", "read_then_summarize"),
    "linkedin_activity": ("linkedin", "read_then_summarize"),
    "linkedin_browser_post": ("linkedin", "draft"),
    "web_search": ("web", "search"),
    "generic_chat": ("chat", "answer"),
}

DOMAIN_ROUTE_FALLBACK: dict[str, str] = {
    "gmail": "gmail_read",
    "calendar": "calendar_read",
    "google_setup": "google_oauth_setup",
    "screen": "screen_read",
    "terminal": "terminal_error",
    "project": "project_factory",
    "cursor": "cursor_work",
    "browser": "browser_or_video",
    "spotify": "spotify",
    "desktop": "desktop_control",
    "beeper": "beeper_messages",
    "linkedin": "linkedin_browser_post",
    "web": "web_search",
    "status": "local_status",
    "chat": "generic_chat",
}


@dataclass(frozen=True)
class StructuredInterpretation:
    goal: str
    domain: str
    outcome: str
    route: str
    confidence: float
    should_execute: bool
    needs_clarification: bool
    clarification_question: str
    reasoning_summary: str
    candidate_routes: tuple[str, ...]
    risk_level: str
    evidence_required: tuple[str, ...]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "oui"}
    return default


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return " ".join(str(value).split())


def _as_tuple(value: Any, allowed: tuple[str, ...] | None = None, limit: int = 6) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for item in value:
        text = _as_text(item)
        if not text:
            continue
        if allowed and text not in allowed:
            continue
        if text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return tuple(items)


def _normalize_route(raw_route: str, domain: str, base_route: str) -> str:
    route = raw_route.strip().lower().replace("-", "_")
    if route in {"map", "map_preview", "map3d", "google_maps", "google_earth"}:
        return "browser_or_video"
    if route in ALLOWED_ROUTES:
        return route
    if domain == "linkedin" and base_route == "linkedin_activity":
        return "linkedin_activity"
    return DOMAIN_ROUTE_FALLBACK.get(domain, base_route if base_route in ALLOWED_ROUTES else "generic_chat")


def _normalize_domain(raw_domain: str, route: str, base_domain: str) -> str:
    domain = raw_domain.strip().lower().replace("-", "_")
    if domain in ALLOWED_DOMAINS:
        return domain
    return ROUTE_DEFAULTS.get(route, (base_domain, "answer"))[0]


def _normalize_outcome(raw_outcome: str, route: str, base_outcome: str) -> str:
    outcome = raw_outcome.strip().lower().replace("-", "_")
    if outcome in ALLOWED_OUTCOMES:
        return outcome
    return ROUTE_DEFAULTS.get(route, ("chat", base_outcome))[1]


def _build_interpreter_prompt(
    message: str,
    conversation_context: list[dict[str, str]],
    base_frame: UnderstandingFrame,
    trusted_actions: bool,
) -> str:
    recent = []
    for item in conversation_context[-8:]:
        role = item.get("role")
        content = _as_text(item.get("content"))[:600]
        if role in {"user", "assistant"} and content:
            recent.append(f"{role}: {content}")

    return (
        "Message de Victor:\n"
        f"{message}\n\n"
        "Contexte recent:\n"
        f"{chr(10).join(recent) if recent else 'Aucun.'}\n\n"
        "Analyse deterministe actuelle:\n"
        f"- domaine={base_frame.primary_domain}\n"
        f"- resultat={base_frame.expected_outcome}\n"
        f"- route={base_frame.action_plan.route}\n"
        f"- objectif={base_frame.interpreted_goal}\n"
        f"- confiance={base_frame.intent.confidence}\n"
        f"- session_fiable={trusted_actions}\n\n"
        "Working memory active:\n"
        f"- summary={base_frame.cognitive_memory_summary or 'aucune'}\n"
        f"- clusters={', '.join(base_frame.cognitive_memory_clusters) if base_frame.cognitive_memory_clusters else 'aucun'}\n"
        f"- souvenirs={base_frame.cognitive_memory_count}\n"
        f"- skills={', '.join(base_frame.cognitive_skill_keys) if base_frame.cognitive_skill_keys else 'aucun'}\n\n"
        "Routes autorisees:\n"
        f"{', '.join(ALLOWED_ROUTES)}\n\n"
        "Domaines autorises:\n"
        f"{', '.join(ALLOWED_DOMAINS)}\n\n"
        "Resultats autorises:\n"
        f"{', '.join(ALLOWED_OUTCOMES)}"
    )


INTERPRETER_SYSTEM_PROMPT = """
Tu es le routeur cognitif local d'Eva. Tu n'es pas le chatbot final.
Tu transformes la demande de Victor en JSON operationnel pour un assistant local Windows.

Principes:
- comprendre l'objectif reel avant de repondre;
- ne pas demander de precision si une interpretation raisonnable et sure existe;
- executer les actions locales sures si la session est fiable;
- demander confirmation seulement pour envoyer, publier, supprimer, git push, achat/paiement ou action irreversible;
- ne jamais inventer qu'une action a ete faite;
- ne jamais utiliser OpenAI, ChatGPT API ou un cloud payant comme dependance;
- ne pas exposer de raisonnement long: fournir seulement une synthese operationnelle courte.

Retourne uniquement un objet JSON avec ces champs:
{
  "goal": "objectif reformule en une phrase",
  "domain": "un domaine autorise",
  "outcome": "un resultat autorise",
  "route": "une route autorisee",
  "confidence": 0.0,
  "should_execute": true,
  "needs_clarification": false,
  "clarification_question": "",
  "reasoning_summary": "synthese courte de la decision",
  "candidate_routes": ["route principale", "plan B"],
  "risk_level": "read_only|local_action|external_draft|critical",
  "evidence_required": ["preuve attendue 1", "preuve attendue 2"]
}
""".strip()


def _interpret_payload(payload: dict[str, Any], base_frame: UnderstandingFrame) -> StructuredInterpretation:
    base_route = str(base_frame.action_plan.route)
    raw_domain = _as_text(payload.get("domain"), str(base_frame.primary_domain))
    route = _normalize_route(_as_text(payload.get("route"), base_route), raw_domain, base_route)
    domain = _normalize_domain(raw_domain, route, str(base_frame.primary_domain))
    outcome = _normalize_outcome(_as_text(payload.get("outcome"), str(base_frame.expected_outcome)), route, str(base_frame.expected_outcome))
    confidence = _as_float(payload.get("confidence"), base_frame.intent.confidence)
    candidate_routes = _as_tuple(payload.get("candidate_routes"), ALLOWED_ROUTES)
    if route not in candidate_routes:
        candidate_routes = (route, *candidate_routes)

    return StructuredInterpretation(
        goal=_as_text(payload.get("goal"), base_frame.interpreted_goal),
        domain=domain,
        outcome=outcome,
        route=route,
        confidence=confidence,
        should_execute=_as_bool(payload.get("should_execute"), True),
        needs_clarification=_as_bool(payload.get("needs_clarification"), False),
        clarification_question=_as_text(payload.get("clarification_question")),
        reasoning_summary=_as_text(payload.get("reasoning_summary"), "Second regard local applique."),
        candidate_routes=candidate_routes[:5],
        risk_level=_as_text(payload.get("risk_level"), str(base_frame.safety_level)),
        evidence_required=_as_tuple(payload.get("evidence_required"), limit=5),
    )


def _should_accept_interpretation(
    interpretation: StructuredInterpretation,
    base_frame: UnderstandingFrame,
) -> bool:
    normalized = base_frame.normalized_message
    mail_context = bool(re.search(r"\b(?:mail|mails|email|emails|gmail)\b", normalized))
    cursor_context = any(marker in normalized for marker in ("cursor", "codex", "projet", "workspace")) or bool(
        re.search(r"\brepo(?:sitory)?\b", normalized)
    )
    news_context = has_news_context(normalized)

    if news_context and interpretation.route not in {"web_search", "generic_chat"}:
        return False

    if news_context and interpretation.domain not in {"web", "chat"}:
        return False

    if base_frame.primary_domain == "gmail" and interpretation.route == "cursor_work" and not cursor_context:
        return False

    if mail_context and interpretation.route == "cursor_work" and not cursor_context:
        return False

    if base_frame.primary_domain == "project" and interpretation.route == "cursor_work":
        return False

    if (
        base_frame.action_plan.route == "linkedin_activity"
        and interpretation.route == "linkedin_browser_post"
        and base_frame.expected_outcome in {"read", "read_then_summarize", "read_then_open"}
    ):
        return False

    base_route = str(base_frame.action_plan.route)
    action_domain = base_frame.primary_domain in {
        "gmail",
        "calendar",
        "screen",
        "terminal",
        "project",
        "cursor",
        "browser",
        "spotify",
        "desktop",
        "beeper",
        "linkedin",
        "web",
    }

    if base_route != "generic_chat" and interpretation.route == "generic_chat" and base_frame.intent.confidence >= 0.7:
        return False

    if action_domain and interpretation.domain == "chat" and base_frame.intent.confidence >= 0.7:
        return False

    if interpretation.confidence < settings.eva_reasoning_min_confidence:
        return False

    if base_route == "generic_chat" and interpretation.route != "generic_chat":
        return True

    if interpretation.route != base_route and interpretation.confidence >= base_frame.intent.confidence:
        return True

    if interpretation.domain != base_frame.primary_domain and interpretation.confidence >= 0.7:
        return True

    return interpretation.confidence >= max(settings.eva_reasoning_min_confidence, base_frame.intent.confidence + 0.12)


def apply_interpretation_to_frame(
    base_frame: UnderstandingFrame,
    interpretation: StructuredInterpretation,
    trusted_actions: bool,
) -> UnderstandingFrame:
    route = cast(PlanRoute, interpretation.route)
    domain = cast(PrimaryDomain, interpretation.domain)
    outcome = cast(ExpectedOutcome, interpretation.outcome)
    safety_level = cast(SafetyLevel, _safety_level(domain, outcome, base_frame.normalized_message))
    required_evidence = interpretation.evidence_required or _required_evidence(domain, outcome)
    action_plan = build_action_plan_for_route(
        route=route,
        goal=interpretation.goal or base_frame.interpreted_goal,
        confidence=interpretation.confidence,
        trusted_actions=trusted_actions,
        caution=base_frame.intent.caution,
    )

    clarification_question = ""
    if interpretation.needs_clarification and safety_level == "critical":
        clarification_question = interpretation.clarification_question

    return replace(
        base_frame,
        interpreted_goal=interpretation.goal or base_frame.interpreted_goal,
        primary_domain=domain,
        expected_outcome=outcome,
        action_plan=action_plan,
        safety_level=safety_level,
        required_evidence=required_evidence,
        tool_preference=_tool_preference(domain),
        clarification_question=clarification_question,
        reasoning_summary=interpretation.reasoning_summary,
        reasoning_confidence=interpretation.confidence,
        reasoning_model=settings.ollama_reasoning_model,
        reasoning_routes=interpretation.candidate_routes,
    )


async def refine_understanding_with_ollama(
    message: str,
    conversation_context: list[dict[str, str]],
    base_frame: UnderstandingFrame,
    trusted_actions: bool,
) -> UnderstandingFrame:
    if not settings.eva_reasoning_enabled:
        return base_frame

    try:
        payload = await ask_ollama_json(
            INTERPRETER_SYSTEM_PROMPT,
            _build_interpreter_prompt(message, conversation_context, base_frame, trusted_actions),
            model=settings.ollama_reasoning_model,
            timeout_seconds=settings.ollama_reasoning_timeout_seconds,
            temperature=0.05,
        )
        interpretation = _interpret_payload(payload, base_frame)
    except OllamaClientError:
        return replace(
            base_frame,
            reasoning_summary="Second regard local indisponible; route deterministe conservee.",
            reasoning_confidence=base_frame.intent.confidence,
            reasoning_model=settings.ollama_reasoning_model,
            reasoning_routes=(str(base_frame.action_plan.route),),
        )

    if not _should_accept_interpretation(interpretation, base_frame):
        return replace(
            base_frame,
            reasoning_summary=interpretation.reasoning_summary or "Route deterministe conservee.",
            reasoning_confidence=interpretation.confidence,
            reasoning_model=settings.ollama_reasoning_model,
            reasoning_routes=interpretation.candidate_routes or (str(base_frame.action_plan.route),),
        )

    return apply_interpretation_to_frame(base_frame, interpretation, trusted_actions)

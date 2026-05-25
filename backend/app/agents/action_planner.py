import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.agents.intent_router import UserIntent
from app.security.action_policy import ActionPolicyLevel


PlanRoute = Literal[
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
]

StepStatus = Literal["done", "ready", "blocked"]


@dataclass(frozen=True)
class ActionPlanStep:
    label: str
    status: StepStatus = "ready"
    tool: str | None = None
    auto: bool = False


@dataclass(frozen=True)
class ActionPlan:
    route: PlanRoute
    goal: str
    confidence: float
    policy_level: ActionPolicyLevel
    trusted_actions: bool
    steps: tuple[ActionPlanStep, ...]
    caution: str = ""


def _normalise(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _route_from_message(message: str, intent: UserIntent) -> PlanRoute:
    text = _normalise(message)

    if intent.name in {
        "terminal_error",
        "screen_read",
        "google_oauth_setup",
        "calendar_read",
        "gmail_read",
        "gmail_reply_audit",
        "gmail_reply_draft",
        "project_factory",
        "cursor_work",
        "linkedin_activity",
        "linkedin_browser_post",
        "web_search",
    }:
        return intent.name

    if _has_any(text, ("spotify", "musique", "playlist", "lance une chanson", "mets ")):
        return "spotify"

    if _has_any(text, ("beeper", "message beeper", "messages beeper", "mes messages")) and "linkedin" not in text:
        return "beeper_messages"

    if "linkedin" in text and _has_any(
        text,
        (
            "activite",
            "activites",
            "notification",
            "notifications",
            "message",
            "messages",
            "compte",
            "abonnes",
            "abonne",
            "followers",
            "connexion",
            "connexions",
            "invitations",
            "commentaires",
            "likes",
            "statistiques",
            "stats",
            "nouveaux",
            "nouvelles",
        ),
    ):
        return "linkedin_activity"

    if "linkedin" in text and _has_any(
        text,
        (
            "post",
            "contenu",
            "commentaire",
            "publie",
            "publier",
            "poster",
            "ouvre",
            "ouvrir",
            "dreamlense",
            "redige",
            "ecris",
            "idee",
        ),
    ):
        return "linkedin_browser_post"

    if _has_any(text, ("clique", "click", "appuie", "presse", "touche", "play", "pause")):
        return "desktop_control"

    if _has_any(
        text,
        (
            "youtube",
            "video",
            "tuto",
            "tutoriel",
            "carte",
            "cartz",
            "map",
            "maps",
            "google maps",
            "google earth",
            "plan de",
            "ouvre brave",
            "ouvre le navigateur",
            "ouvre google",
            "ouvre un onglet",
        ),
    ):
        return "browser_or_video"

    if _has_any(
        text,
        (
            "cherche sur internet",
            "recherche internet",
            "va sur internet",
            "trouve sur internet",
            "cherche web",
            "recherche web",
        ),
    ):
        return "web_search"

    return "generic_chat"


def _policy_for_route(route: PlanRoute) -> ActionPolicyLevel:
    if route in {
        "generic_chat",
        "local_status",
        "calendar_read",
        "gmail_read",
        "gmail_reply_audit",
        "linkedin_activity",
        "web_search",
    }:
        return "read_only"
    if route in {
        "gmail_reply_draft",
        "cursor_work",
        "browser_or_video",
        "spotify",
        "desktop_control",
        "beeper_messages",
        "linkedin_browser_post",
        "project_factory",
    }:
        return "draft_only"
    if route in {"terminal_error", "screen_read", "google_oauth_setup"}:
        return "draft_only"
    return "read_only"


def _tool_for_route(route: PlanRoute) -> str:
    return {
        "terminal_error": "terminal_doctor",
        "screen_read": "screen_reader",
        "google_oauth_setup": "gmail_auth",
        "calendar_read": "google_calendar",
        "gmail_read": "gmail_client",
        "gmail_reply_audit": "gmail_client",
        "gmail_reply_draft": "gmail_client",
        "project_factory": "project_factory",
        "cursor_work": "cursor_bridge",
        "local_status": "doctor",
        "browser_or_video": "browser_assistant",
        "spotify": "spotify_assistant",
        "desktop_control": "desktop_automation",
        "beeper_messages": "beeper_assistant",
        "linkedin_activity": "linkedin_activity",
        "linkedin_browser_post": "linkedin_assistant",
        "web_search": "web_search",
        "generic_chat": "ollama_chat",
    }[route]


def build_action_plan(
    message: str,
    intent: UserIntent,
    trusted_actions: bool,
) -> ActionPlan:
    route = _route_from_message(message, intent)
    return build_action_plan_for_route(
        route=route,
        goal=intent.summary,
        confidence=intent.confidence,
        trusted_actions=trusted_actions,
        caution=intent.caution,
    )


def build_action_plan_for_route(
    route: PlanRoute,
    goal: str,
    confidence: float,
    trusted_actions: bool,
    caution: str = "",
) -> ActionPlan:
    policy_level = _policy_for_route(route)
    tool = _tool_for_route(route)
    can_use_tool = trusted_actions or policy_level == "read_only"

    steps: list[ActionPlanStep] = [
        ActionPlanStep("Comprendre la demande reelle de Victor.", status="done"),
        ActionPlanStep(
            f"Choisir la route: {route} avec confiance {round(confidence * 100)}%.",
            status="done",
        ),
    ]

    if can_use_tool:
        steps.append(
            ActionPlanStep(
                f"Executer le meilleur outil local disponible: {tool}.",
                tool=tool,
                auto=True,
            )
        )
    else:
        steps.append(
            ActionPlanStep(
                "Bloquer l'action locale car la session n'est pas fiable.",
                status="blocked",
                tool=tool,
                auto=False,
            )
        )
        caution = (
            f"{caution} Session non fiable: action locale refusee.".strip()
        )

    steps.append(
        ActionPlanStep(
            "Rendre un resultat factuel: dire ce qui a ete fait, ce qui reste bloque, et le plan B.",
            auto=False,
        )
    )

    return ActionPlan(
        route=route,
        goal=goal,
        confidence=confidence,
        policy_level=policy_level,
        trusted_actions=trusted_actions,
        steps=tuple(steps),
        caution=caution,
    )


def format_action_plan_context(plan: ActionPlan) -> str:
    lines = [
        "Plan interne Eva avant action.",
        f"Objectif interprete: {plan.goal}",
        f"Route: {plan.route}",
        f"Politique: {plan.policy_level}",
        f"Session fiable: {plan.trusted_actions}",
    ]
    if plan.caution:
        lines.append(f"Point de prudence: {plan.caution}")

    lines.append("Etapes:")
    for index, step in enumerate(plan.steps, start=1):
        tool = f" / tool={step.tool}" if step.tool else ""
        auto = " / auto" if step.auto else ""
        lines.append(f"{index}. [{step.status}]{tool}{auto} {step.label}")

    lines.append(
        "Ce plan est interne: ne le recite pas systematiquement. Utilise-le pour agir dans le bon ordre."
    )
    return "\n".join(lines)


def action_plan_to_dict(plan: ActionPlan) -> dict[str, object]:
    return {
        "route": plan.route,
        "goal": plan.goal,
        "confidence": plan.confidence,
        "policy_level": plan.policy_level,
        "trusted_actions": plan.trusted_actions,
        "caution": plan.caution,
        "steps": [
            {
                "label": step.label,
                "status": step.status,
                "tool": step.tool,
                "auto": step.auto,
            }
            for step in plan.steps
        ],
    }

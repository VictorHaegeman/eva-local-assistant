from dataclasses import dataclass

from app.agents.understanding import UnderstandingFrame
from app.cognition.state import CognitiveState, goal_frame_from_understanding
from app.cognition.tool_result import ToolResult


PASSIVE_REFUSAL_MARKERS = (
    "je ne peux pas",
    "je suis desole",
    "je suis désolé",
    "je n'ai pas acces",
    "je n'ai pas accès",
    "je ne suis pas capable",
    "en tant qu'assistant",
    "en tant qu'ia",
)


@dataclass(frozen=True)
class ProblemResolution:
    problem_type: str
    summary: str
    alternate_routes: tuple[str, ...] = ()
    safe_actions: tuple[str, ...] = ()
    blocked_by_policy: bool = False
    confidence: float = 0.7


def looks_like_passive_refusal(answer: str) -> bool:
    normalized = " ".join(answer.lower().split())
    return any(marker in normalized for marker in PASSIVE_REFUSAL_MARKERS)


def _draft_route_for_domain(domain: str) -> tuple[str, ...]:
    if domain == "gmail":
        return ("gmail_reply_draft", "gmail_read")
    if domain == "linkedin":
        return ("linkedin_browser_post", "web_search")
    if domain in {"project", "cursor"}:
        return ("cursor_work", "project_factory", "web_search")
    if domain in {"desktop", "screen"}:
        return ("screen_read", "desktop_control")
    if domain == "browser":
        return ("web_search",)
    return ("web_search",)


def _tool_recovery_routes(tool: str, domain: str) -> tuple[str, ...]:
    if tool == "gmail_client":
        return ("gmail_read", "web_search")
    if tool == "browser_assistant":
        return ("web_search", "screen_read")
    if tool == "cursor_bridge":
        return ("project_factory", "web_search")
    if tool == "project_factory":
        return ("cursor_work", "web_search")
    if tool == "spotify_assistant":
        return ("browser_or_video", "web_search")
    if tool == "desktop_automation":
        return ("screen_read", "browser_or_video", "web_search")
    if tool == "screen_reader":
        return ("desktop_control", "web_search")
    if tool == "beeper_assistant":
        return ("screen_read", "desktop_control")
    if tool in {"linkedin_assistant", "linkedin_activity"}:
        return ("web_search", "browser_or_video")
    return _draft_route_for_domain(domain)


def diagnose_problem(
    result: ToolResult,
    understanding: UnderstandingFrame,
    trusted_actions: bool,
) -> ProblemResolution:
    normalized_error = " ".join((result.error or "").lower().split())
    domain = understanding.primary_domain

    if result.status == "blocked":
        if "session fiable" in normalized_error or "telegram autorise" in normalized_error:
            return ProblemResolution(
                problem_type="permission",
                summary=(
                    "La demande demande une action locale, mais le canal courant n'est pas marque "
                    "comme suffisamment fiable pour piloter le PC."
                ),
                alternate_routes=("web_search",),
                safe_actions=(
                    "chercher une alternative web gratuite si cela peut aider",
                    "preparer les etapes exactes a executer depuis Telegram autorise ou le PC local",
                    "garder une trace dans la reponse au lieu d'abandonner",
                ),
                blocked_by_policy=True,
                confidence=0.86,
            )

        return ProblemResolution(
            problem_type="safety",
            summary="La politique locale bloque l'action brute, donc Eva doit tenter une version sure.",
            alternate_routes=_draft_route_for_domain(domain),
            safe_actions=(
                "remplacer l'action critique par un brouillon ou une preparation",
                "donner une preuve locale si un outil a quand meme avance",
                "ne pas inventer que l'action finale est faite",
            ),
            blocked_by_policy=True,
            confidence=0.82,
        )

    if result.status == "failed":
        return ProblemResolution(
            problem_type="tool_failure",
            summary=(
                f"L'outil {result.tool} n'a pas donne de resultat fiable. "
                "Eva doit changer de route au lieu de repondre passivement."
            ),
            alternate_routes=_tool_recovery_routes(result.tool, domain),
            safe_actions=(
                "essayer une route alternative non critique",
                "utiliser la recherche web gratuite si l'outil local echoue",
                "rapporter les pistes tentees et le meilleur plan de reprise",
            ),
            confidence=0.74,
        )

    return ProblemResolution(
        problem_type="weak_result",
        summary="Le resultat n'est pas assez prouve pour etre annonce comme termine.",
        alternate_routes=_tool_recovery_routes(result.tool, domain),
        safe_actions=(
            "chercher une preuve locale supplementaire",
            "relancer une route alternative",
            "repondre avec un statut verifie seulement",
        ),
        confidence=0.68,
    )


def problem_routes_for_result(
    result: ToolResult,
    understanding: UnderstandingFrame,
    trusted_actions: bool,
) -> tuple[str, ...]:
    resolution = diagnose_problem(result, understanding, trusted_actions)
    return tuple(
        route
        for route in resolution.alternate_routes
        if route not in {"generic_chat"} and (trusted_actions or route == "web_search")
    )


def problem_routes_for_state(
    state: CognitiveState,
    understanding: UnderstandingFrame,
) -> tuple[str, ...]:
    if not state.tool_results:
        return ()
    return problem_routes_for_result(
        state.tool_results[-1],
        understanding,
        trusted_actions=state.trusted_actions,
    )


def build_problem_solver_response(
    message: str,
    state: CognitiveState,
    resolution: ProblemResolution,
) -> str:
    lines = [
        "Mode resolution active.",
        f"Objectif compris: {state.goal.goal or message}",
        f"Diagnostic: {resolution.summary}",
    ]

    if state.tool_results:
        lines.append("")
        lines.append("Pistes tentees:")
        for result in state.tool_results[-5:]:
            detail = result.error or (result.evidence[0] if result.evidence else "aucune preuve locale")
            lines.append(f"- {result.tool}: {result.status} - {detail}")

    if resolution.safe_actions:
        lines.append("")
        lines.append("Plan de reprise:")
        lines.extend(f"- {action}" for action in resolution.safe_actions)

    if resolution.alternate_routes:
        routes = ", ".join(route.replace("_", " ") for route in resolution.alternate_routes[:4])
        lines.append(f"\nRoutes alternatives candidates: {routes}.")

    if resolution.blocked_by_policy:
        lines.append(
            "\nGarde-fou: je peux contourner par une preparation, un brouillon, une recherche ou une action locale sure; "
            "je ne dois pas maquiller une action critique non executee."
        )
    else:
        lines.append("\nEtat: aucune route n'a encore donne une preuve suffisante, donc je garde le diagnostic exploitable.")

    return "\n".join(lines)


def build_direct_problem_solver_response(
    message: str,
    understanding: UnderstandingFrame,
    tool: str,
    reason: str,
    trusted_actions: bool,
    channel: str = "web",
    next_actions: tuple[str, ...] = (),
) -> str:
    state = CognitiveState(
        goal=goal_frame_from_understanding(understanding),
        channel=channel,
        trusted_actions=trusted_actions,
    )
    state.add_result(
        ToolResult(
            tool=tool,
            status="blocked",
            error=reason,
            next_actions=next_actions,
            confidence=0.86,
        )
    )
    resolution = diagnose_problem(state.tool_results[-1], understanding, trusted_actions)
    return build_problem_solver_response(message, state, resolution)


def build_exception_recovery_response(message: str, error: str) -> str:
    clean_error = " ".join(str(error).split())[:900] or "erreur inconnue"
    return "\n".join(
        [
            "Mode resolution active.",
            f"Objectif compris: {message}",
            f"Blocage detecte: {clean_error}",
            "",
            "Plan de reprise:",
            "- reprendre le contexte recent avant de reclasser la demande;",
            "- chercher un outil local ou une route web gratuite adaptee;",
            "- si un connecteur manque, expliquer exactement le connecteur ou le flag a activer;",
            "- garder une trace exploitable au lieu de terminer sur un refus brut.",
        ]
    )


def build_passive_refusal_recovery(message: str) -> str:
    return "\n".join(
        [
            "Mode resolution active.",
            f"Objectif compris: {message}",
            "Diagnostic: la reponse brute ressemblait a un refus passif, donc elle est remplacee.",
            "",
            "Plan de reprise:",
            "- reclasser l'intention avec la memoire et les skills;",
            "- chercher un outil local ou une route web gratuite;",
            "- si l'action finale est critique, produire une preparation verifiable au lieu d'abandonner.",
        ]
    )

from dataclasses import dataclass

from app.agents.understanding import UnderstandingFrame
from app.cognition.problem_store import record_problem_event
from app.cognition.state import CognitiveState, goal_frame_from_understanding
from app.cognition.tool_result import ToolResult
from app.integrations.gmail_client import is_google_reauth_error


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
        return ("linkedin_activity", "linkedin_browser_post", "browser_or_video")
    if domain in {"project", "cursor"}:
        return ("cursor_work", "project_factory")
    if domain in {"desktop", "screen"}:
        return ("screen_read", "desktop_control")
    if domain == "spotify":
        return ("spotify", "browser_or_video")
    if domain == "beeper":
        return ("beeper_messages", "screen_read")
    if domain == "calendar":
        return ("calendar_read",)
    if domain == "browser":
        return ("web_search",)
    return ("web_search",)


def _tool_recovery_routes(tool: str, domain: str) -> tuple[str, ...]:
    if tool == "gmail_client":
        return ("gmail_reply_audit", "gmail_read", "gmail_reply_draft")
    if tool == "browser_assistant":
        return ("web_search", "screen_read")
    if tool == "cursor_bridge":
        return ("project_factory", "web_search")
    if tool == "project_factory":
        return ("cursor_work", "web_search")
    if tool == "spotify_assistant":
        return ("spotify", "browser_or_video")
    if tool == "desktop_automation":
        return ("screen_read", "desktop_control")
    if tool == "screen_reader":
        return ("desktop_control", "screen_read")
    if tool == "beeper_assistant":
        return ("screen_read", "desktop_control")
    if tool in {"linkedin_assistant", "linkedin_activity"}:
        return ("linkedin_activity", "browser_or_video")
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
            permission_routes = (
                ("web_search",)
                if domain in {"browser", "web"}
                else _draft_route_for_domain(domain)
            )
            return ProblemResolution(
                problem_type="permission",
                summary=(
                    "Le canal courant n'est pas marque comme session fiable pour piloter le PC. "
                    "Eva bascule donc en mode preparation et recherche de chemin alternatif."
                ),
                alternate_routes=permission_routes,
                safe_actions=(
                    "utiliser uniquement une route alternative coherente avec le domaine demande",
                    "preparer les etapes exactes a executer depuis Telegram autorise ou le PC local",
                    "journaliser le blocage dans le resolver pour reprendre ensuite",
                ),
                blocked_by_policy=True,
                confidence=0.86,
            )

        return ProblemResolution(
            problem_type="safety",
            summary="La politique locale bloque l'action brute; Eva tente une version sure ou un brouillon verifiable.",
            alternate_routes=_draft_route_for_domain(domain),
            safe_actions=(
                "remplacer l'action critique par un brouillon ou une preparation",
                "donner une preuve locale si un outil a quand meme avance",
                "s'arreter avant l'action irreversible si aucune preuve ne permet de continuer proprement",
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
    latest_result = state.tool_results[-1] if state.tool_results else None
    event = None
    if latest_result:
        event = record_problem_event(
            message=message,
            domain=state.goal.domain,
            expected_outcome=state.goal.expected_outcome,
            problem_type=resolution.problem_type,
            summary=resolution.summary,
            tool=latest_result.tool,
            status=latest_result.status,
            error=latest_result.error,
            alternate_routes=resolution.alternate_routes,
            safe_actions=resolution.safe_actions,
            trusted_actions=state.trusted_actions,
        )

    if latest_result and latest_result.tool == "gmail_client" and is_google_reauth_error(latest_result.error):
        lines = [
            "Je n'ai pas pu lire tes mails reels pour l'instant.",
            "",
            "La connexion Google locale a expire ou a ete revoquee. Le token Gmail/Calendar doit etre regenere avant qu'Eva puisse relire Gmail.",
            "",
            "Je ne vais pas remplacer ca par une recherche web ni inventer des mails.",
            "",
            "Action a faire:",
            "- depuis Eva: panneau Gmail > Reconnecter scopes;",
            "- depuis Telegram: envoie /google;",
            "- valide le compte Google dans la fenetre ouverte sur le PC, puis renvoie ta demande.",
        ]
        return "\n".join(lines)

    latest_tool = latest_result.tool if latest_result else "outil local"
    latest_status = latest_result.status if latest_result else "bloque"
    public_blocker = resolution.summary
    if latest_result and latest_result.error:
        public_blocker = _public_error_summary(latest_result)

    lines = [
        "Je n'ai pas encore un resultat fiable.",
        "",
        f"Objectif compris: {state.goal.goal or message}",
        f"Blocage: {public_blocker}",
    ]
    if state.tool_results:
        lines.append("")
        lines.append(f"Dernier essai: {_tool_label(latest_tool)} ({latest_status}).")

    if resolution.safe_actions:
        lines.append("")
        lines.append("Prochaine reprise:")
        lines.append(f"- {_public_next_action(resolution)}")

    if resolution.alternate_routes:
        routes = ", ".join(_route_label(route) for route in resolution.alternate_routes[:3])
        lines.append(f"- Routes possibles: {routes}.")

    if resolution.blocked_by_policy:
        lines.append(
            ""
            "Garde-fou: je peux preparer, lire ou creer un brouillon, mais je ne maquille pas une action critique non executee."
        )
    else:
        lines.append("")
        lines.append("Je garde le contexte et je reprendrai par une route plus adaptee au prochain essai.")

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
    if is_google_reauth_error(clean_error):
        return "\n".join(
            [
                "Je n'ai pas pu acceder a Google pour l'instant.",
                "",
                "La connexion Gmail/Calendar locale a expire ou a ete revoquee. Eva doit reconnecter Google avant de lire tes mails reels.",
                "",
                "Action a faire: envoie /google depuis Telegram ou clique Reconnecter scopes dans le panneau Gmail.",
            ]
        )
    return "\n".join(
        [
            "Je n'ai pas encore un resultat fiable.",
            f"Objectif compris: {message}",
            f"Blocage detecte: {_public_error_text(clean_error)}",
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
            "Je reprends au lieu de bloquer.",
            f"Objectif compris: {message}",
            "La reponse brute ressemblait a un refus passif, donc elle est remplacee par une reprise d'action.",
            "",
            "Plan de reprise:",
            "- reclasser l'intention avec la memoire et les skills;",
            "- chercher un outil local ou une route web gratuite;",
            "- si l'action finale est critique, produire une preparation verifiable au lieu d'abandonner.",
        ]
    )


def _public_error_text(error: str) -> str:
    if is_google_reauth_error(error):
        return "connexion Google expiree ou revoquee"
    clean = " ".join(str(error).split())
    if not clean:
        return "preuve locale absente"
    if len(clean) > 180:
        return f"{clean[:177]}..."
    return clean


def _public_error_summary(result: ToolResult) -> str:
    if result.tool == "gmail_client" and is_google_reauth_error(result.error):
        return "connexion Google a refaire avant de lire Gmail"
    if result.status == "blocked":
        return "action locale bloquee par la politique de securite"
    if result.status == "failed":
        return f"{_tool_label(result.tool)} n'a pas donne de preuve fiable"
    return _public_error_text(result.error)


def _tool_label(tool: str) -> str:
    return {
        "gmail_client": "Gmail",
        "browser_assistant": "navigateur",
        "cursor_bridge": "Cursor",
        "project_factory": "Project Factory",
        "spotify_assistant": "Spotify",
        "desktop_automation": "controle PC",
        "screen_reader": "lecture ecran",
        "beeper_assistant": "Beeper",
        "linkedin_assistant": "LinkedIn",
        "linkedin_activity": "LinkedIn",
        "web_search": "recherche web",
    }.get(tool, tool.replace("_", " "))


def _route_label(route: str) -> str:
    return {
        "gmail_reply_audit": "audit Gmail",
        "gmail_read": "lecture Gmail",
        "gmail_reply_draft": "brouillon Gmail",
        "web_search": "recherche web",
        "screen_read": "lecture ecran",
        "desktop_control": "controle PC",
        "browser_or_video": "navigateur",
        "cursor_work": "Cursor",
        "project_factory": "Project Factory",
        "linkedin_activity": "LinkedIn",
    }.get(route, route.replace("_", " "))


def _public_next_action(resolution: ProblemResolution) -> str:
    if resolution.problem_type == "permission":
        return "reprendre par une route sure ou depuis un canal autorise"
    if resolution.problem_type == "tool_failure":
        return "essayer une autre route locale coherente avec la demande"
    if resolution.problem_type == "safety":
        return "preparer une version brouillon ou reversible"
    return "chercher une preuve locale supplementaire avant de conclure"

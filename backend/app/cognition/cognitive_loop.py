from dataclasses import dataclass
from typing import Any

from app.agents.understanding import UnderstandingFrame
from app.cognition.critic import critic_report_to_dict, criticize_response
from app.cognition.problem_solver import (
    build_problem_solver_response,
    diagnose_problem,
    problem_routes_for_result,
)
from app.cognition.response_builder import build_blocked_response, build_critic_response
from app.cognition.retry_policy import fallback_for_result
from app.cognition.state import (
    CognitiveState,
    cognitive_state_to_dict,
    goal_frame_from_understanding,
)
from app.cognition.tool_result import ToolResult, tool_result_to_dict
from app.cognition.verifier import verify_result
from app.config import settings
from app.integrations.beeper_assistant import beeper_response_has_useful_content, build_beeper_chat_response
from app.integrations.browser_actions import open_browser_from_message
from app.integrations.browser_assistant import open_assisted_browser_from_message
from app.integrations.browser import open_url
from app.integrations.cursor_agent_setup import (
    format_cursor_agent_setup_response,
    setup_cursor_agent,
)
from app.integrations.desktop_chat import execute_desktop_control_from_message
from app.integrations.gmail_chat import build_gmail_chat_response
from app.integrations.linkedin_assistant import build_linkedin_activity_response, build_linkedin_chat_response
from app.integrations.map_preview import build_map_preview_from_message
from app.integrations.spotify_assistant import open_spotify_from_message
from app.project_factory.automation import auto_execute_project_factory_actions, format_project_factory_results
from app.project_factory.planner import create_project_factory_actions
from app.projects.project_chat import (
    build_chat_cursor_prompt_response,
    build_cursor_work_session_response,
)
from app.screen.visual_action import analyze_visual_action, format_visual_action_response
from app.screen.screen_navigator import (
    format_screen_navigation_response,
    navigate_screen,
    wants_screen_navigation,
)
from app.web.web_search import detect_web_search_query, format_web_results, search_web


class CognitiveLoopError(Exception):
    """Raised when the cognitive loop cannot execute a selected tool."""


@dataclass(frozen=True)
class CognitiveLoopResult:
    handled: bool
    message: dict[str, Any] | None = None
    state: CognitiveState | None = None
    critic: dict[str, object] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "handled": self.handled,
            "message": self.message,
            "state": cognitive_state_to_dict(self.state) if self.state else None,
            "critic": self.critic,
        }


@dataclass(frozen=True)
class RouteExecution:
    content: str
    result: ToolResult
    selected_route: str
    requires_action: bool = True
    web_preview: dict[str, Any] | None = None


ACTION_ROUTES = {
    "browser_or_video",
    "cursor_agent_setup",
    "cursor_work",
    "gmail_read",
    "gmail_reply_audit",
    "gmail_reply_draft",
    "spotify",
    "desktop_control",
    "beeper_messages",
    "linkedin_activity",
    "linkedin_browser_post",
    "project_factory",
    "web_search",
}


ROUTE_LABELS = {
    "map_preview": "Carte integree",
    "map3d": "Vue 3D",
    "web_search": "Recherche web",
    "browser_or_video": "Navigateur",
    "cursor_work": "Projet / Cursor",
    "cursor_agent_setup": "Setup Cursor Agent",
    "gmail_read": "Gmail lecture",
    "gmail_reply_audit": "Audit reponses",
    "gmail_reply_draft": "Brouillon Gmail",
    "spotify": "Spotify",
    "desktop_control": "Controle PC",
    "beeper_messages": "Beeper",
    "linkedin_activity": "Activite LinkedIn",
    "linkedin_browser_post": "LinkedIn",
    "project_factory": "Project Factory",
    "generic_chat": "Reponse directe",
}


def _blocked(tool: str, reason: str, next_actions: tuple[str, ...] = ()) -> ToolResult:
    return ToolResult(
        tool=tool,
        status="blocked",
        evidence=(),
        error=reason,
        next_actions=next_actions,
        confidence=0.95,
    )


def _failed(
    tool: str,
    error: str,
    next_actions: tuple[str, ...] = (),
    confidence: float = 0.35,
) -> ToolResult:
    return ToolResult(
        tool=tool,
        status="failed",
        error=error,
        next_actions=next_actions,
        confidence=confidence,
    )


def _success(
    tool: str,
    evidence: tuple[str, ...],
    data: dict[str, Any] | None = None,
    confidence: float = 0.86,
) -> ToolResult:
    return verify_result(
        ToolResult(
            tool=tool,
            status="success",
            evidence=evidence,
            data=data or {},
            confidence=confidence,
        )
    )


def _requires_trusted(route: str) -> bool:
    return route in {
        "browser_or_video",
        "cursor_work",
        "cursor_agent_setup",
        "gmail_read",
        "gmail_reply_audit",
        "gmail_reply_draft",
        "screen_read",
        "spotify",
        "desktop_control",
        "beeper_messages",
        "linkedin_activity",
        "linkedin_browser_post",
    }


def _max_reasoning_attempts() -> int:
    base = max(1, min(settings.eva_reasoning_max_attempts, 8))
    if not settings.eva_problem_solver_enabled:
        return base
    return max(base, min(max(settings.eva_problem_solver_max_cycles, 1), 8))


def _tool_for_route(route: str, understanding: UnderstandingFrame) -> str:
    return {
        "browser_or_video": "browser_assistant",
        "cursor_work": "cursor_bridge",
        "cursor_agent_setup": "cursor_agent_setup",
        "gmail_read": "gmail_client",
        "gmail_reply_audit": "gmail_client",
        "gmail_reply_draft": "gmail_client",
        "spotify": "spotify_assistant",
        "desktop_control": "desktop_automation",
        "beeper_messages": "beeper_assistant",
        "linkedin_activity": "linkedin_activity",
        "linkedin_browser_post": "linkedin_assistant",
        "project_factory": "project_factory",
        "web_search": "web_search",
        "screen_read": "screen_reader",
    }.get(route, understanding.tool_preference)


def _route_sequence(route: str, understanding: UnderstandingFrame) -> list[str]:
    domain = understanding.primary_domain
    routes: list[str] = [route]

    for candidate in understanding.reasoning_routes:
        if candidate != "generic_chat":
            routes.append(candidate)

    if domain == "gmail":
        routes.extend(["gmail_read", "gmail_reply_draft"])
    elif domain == "project":
        routes.extend(["project_factory", "cursor_work", "web_search"])
    elif domain == "cursor":
        if route == "cursor_agent_setup":
            routes.extend(["cursor_agent_setup", "web_search"])
        else:
            routes.extend(["cursor_work", "web_search"])
    elif domain == "browser":
        routes.extend(["browser_or_video", "web_search"])
    elif domain == "spotify":
        routes.extend(["spotify", "browser_or_video", "web_search"])
    elif domain in {"desktop", "screen"}:
        routes.extend(["screen_read", "desktop_control", "web_search"])
    elif domain == "beeper":
        routes.extend(["beeper_messages", "screen_read"])
    elif domain == "linkedin":
        if route == "linkedin_activity":
            routes.extend(["linkedin_activity", "web_search", "browser_or_video"])
        else:
            routes.extend(["linkedin_browser_post", "browser_or_video", "web_search"])
    elif domain == "web":
        routes.extend(["web_search", "browser_or_video"])

    if settings.eva_reasoning_web_fallback_enabled and "web_search" not in routes:
        routes.append("web_search")

    unique_routes: list[str] = []
    for candidate in routes:
        if candidate not in unique_routes:
            unique_routes.append(candidate)

    return unique_routes[:_max_reasoning_attempts()]


def _route_options(
    selected_route: str,
    understanding: UnderstandingFrame,
    selected_confidence: float,
) -> list[dict[str, object]]:
    base_options = [selected_route]
    domain = understanding.primary_domain

    if selected_route in {"map_preview", "map3d"}:
        base_options.extend(["web_search", "browser_or_video"])
    elif domain == "gmail":
        base_options.extend(["gmail_read", "gmail_reply_draft", "generic_chat"])
    elif domain == "project" or selected_route == "project_factory":
        base_options.extend(["project_factory", "cursor_work", "web_search", "generic_chat"])
    elif domain == "cursor" or selected_route == "cursor_work":
        if selected_route == "cursor_agent_setup":
            base_options.extend(["web_search", "cursor_work", "generic_chat"])
        else:
            base_options.extend(["cursor_work", "web_search", "generic_chat"])
    elif domain == "browser":
        base_options.extend(["browser_or_video", "web_search", "generic_chat"])
    elif domain == "linkedin":
        if selected_route == "linkedin_activity":
            base_options.extend(["web_search", "browser_or_video", "generic_chat"])
        else:
            base_options.extend(["linkedin_browser_post", "web_search", "generic_chat"])
    elif selected_route == "web_search":
        base_options.extend(["browser_or_video", "generic_chat"])
    else:
        base_options.extend(["web_search", "generic_chat"])

    unique_options: list[str] = []
    for option in base_options:
        if option not in unique_options:
            unique_options.append(option)

    confidence = max(0.3, min(0.98, selected_confidence))
    options: list[dict[str, object]] = []
    for index, option in enumerate(unique_options[:4]):
        score = confidence - (index * 0.14)
        if option == selected_route:
            score = max(score, confidence)
        options.append(
            {
                "key": option,
                "label": ROUTE_LABELS.get(option, option.replace("_", " ")),
                "score": round(max(0.12, score) * 100),
                "selected": option == selected_route,
            }
        )
    return options


def _trace_payload(
    understanding: UnderstandingFrame,
    state: CognitiveState,
    selected_route: str,
) -> dict[str, object]:
    latest_result = state.tool_results[-1] if state.tool_results else None
    evidence = list(latest_result.evidence[:4]) if latest_result else []
    status = latest_result.status if latest_result else "pending"
    confidence = latest_result.confidence if latest_result else understanding.intent.confidence
    selected_label = ROUTE_LABELS.get(selected_route, selected_route.replace("_", " "))

    stages: list[dict[str, object]] = []
    if understanding.cognitive_memory_summary:
        stages.append(
            {
                "key": "recall",
                "label": "Memoire",
                "status": "done",
                "detail": understanding.cognitive_memory_summary,
            }
        )

    if understanding.cognitive_skill_summary:
        stages.append(
            {
                "key": "skills",
                "label": "Skills",
                "status": "done",
                "detail": understanding.cognitive_skill_summary,
            }
        )

    stages.extend(
        [
            {
                "key": "classify",
                "label": "Comprendre",
                "status": "done",
                "detail": f"{understanding.primary_domain} / {understanding.expected_outcome}",
            },
            {
                "key": "route",
                "label": "Choisir",
                "status": "done",
                "detail": selected_label,
                "options": _route_options(selected_route, understanding, confidence),
            },
            {
                "key": "execute",
                "label": "Executer",
                "status": "done" if latest_result and latest_result.status in {"success", "partial"} else status,
                "detail": latest_result.tool if latest_result else understanding.tool_preference,
            },
            {
                "key": "verify",
                "label": "Verifier",
                "status": "done" if evidence else "blocked",
                "detail": evidence[0] if evidence else "preuve absente",
            },
        ]
    )
    if len(state.tool_results) > 1:
        stages.append(
            {
                "key": "retry",
                "label": "Reessayer",
                "status": "done" if latest_result and latest_result.ok else "partial",
                "detail": f"{len(state.tool_results)} pistes tentees",
            }
        )

    if latest_result and latest_result.status in {"failed", "blocked"}:
        resolution = diagnose_problem(latest_result, understanding, state.trusted_actions)
        stages.append(
            {
                "key": "resolver",
                "label": "Resoudre",
                "status": "ready",
                "detail": resolution.summary,
                "options": [
                    {
                        "key": route,
                        "label": ROUTE_LABELS.get(route, route.replace("_", " ")),
                        "score": max(32, round(resolution.confidence * 100) - (index * 11)),
                        "selected": index == 0,
                    }
                    for index, route in enumerate(resolution.alternate_routes[:4])
                ],
            }
        )

    return {
        "title": "Eva pipeline",
        "summary": state.goal.goal,
        "selected": selected_label,
        "confidence": round(max(0.0, min(1.0, confidence)) * 100),
        "status": status,
        "stages": stages,
        "evidence": evidence,
        "attempts": [
            {
                "tool": result.tool,
                "status": result.status,
                "evidence": list(result.evidence[:2]),
                "error": result.error,
                "next_actions": list(result.next_actions[:3]),
            }
            for result in state.tool_results
        ],
        "memory": {
            "summary": understanding.cognitive_memory_summary,
            "clusters": list(understanding.cognitive_memory_clusters),
            "count": understanding.cognitive_memory_count,
        },
        "skills": {
            "summary": understanding.cognitive_skill_summary,
            "keys": list(understanding.cognitive_skill_keys),
        },
    }


def _assistant_payload(
    content: str,
    understanding: UnderstandingFrame,
    state: CognitiveState,
    selected_route: str,
    web_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "cognitive_trace": _trace_payload(understanding, state, selected_route),
    }
    if web_preview:
        payload["web_preview"] = web_preview
    return payload


def build_reasoning_trace(
    understanding: UnderstandingFrame,
    selected_route: str | None = None,
) -> dict[str, object]:
    state = CognitiveState(
        goal=goal_frame_from_understanding(understanding),
        channel="web",
        trusted_actions=understanding.action_plan.trusted_actions,
    )
    return _trace_payload(
        understanding,
        state,
        selected_route or str(understanding.action_plan.route),
    )


async def _map_preview(
    message: str,
    context: str = "",
    trusted_actions: bool = False,
) -> tuple[str, ToolResult, dict[str, Any] | None] | None:
    preview = await build_map_preview_from_message(message, context=context)
    if not preview:
        return None
    web_preview = preview.get("web_preview")
    if not web_preview:
        result = ToolResult(
            tool="map_preview",
            status="failed",
            error=str(preview.get("content", "Carte introuvable.")),
            confidence=0.4,
        )
        return str(preview.get("content", "Carte introuvable.")), result, None

    evidence = [f"Carte preparee via {web_preview.get('provider', 'OpenStreetMap')}"]
    content = str(preview["content"])
    if web_preview.get("type") == "map3d":
        url = str(web_preview.get("url", ""))
        if trusted_actions and url:
            open_url(url)
            evidence.append(f"Ouverture navigateur envoyee vers: {url}")
            content = f"Vue 3D prete: {web_preview.get('label')}.\nOuverture Google Earth Web envoyee a Brave."
        elif url:
            evidence.append(f"Lien 3D prepare: {url}")
            content = f"Vue 3D prete: {web_preview.get('label')}.\nOuvre-la avec le bouton ci-dessous."
    else:
        evidence.append(f"URL embed verifiee: {web_preview.get('embed_url')}")

    result = _success(
        "map_preview",
        tuple(evidence),
        data={"web_preview": web_preview},
        confidence=0.92,
    )
    return content, result, web_preview


async def _execute_route_once(
    message: str,
    understanding: UnderstandingFrame,
    route: str,
    trusted_actions: bool,
) -> RouteExecution | None:
    use_domain_fallback = route == str(understanding.action_plan.route)

    if _requires_trusted(route) and not trusted_actions:
        result = _blocked(
            _tool_for_route(route, understanding),
            "Cette action locale demande une session fiable: PC local ou Telegram autorise.",
            ("refaire la demande depuis le PC local", "ou utiliser ton Telegram autorise"),
        )
        return RouteExecution(
            content=build_blocked_response(result),
            result=result,
            selected_route=route,
        )

    if route in {"gmail_read", "gmail_reply_audit", "gmail_reply_draft"} or (
        use_domain_fallback and understanding.primary_domain == "gmail"
    ):
        content = await build_gmail_chat_response(message, force_list=route == "gmail_read")
        if not content:
            return RouteExecution(
                content="",
                result=_failed(
                    "gmail_client",
                    "Le module Gmail n'a pas produit de resultat exploitable.",
                    fallback_for_result(ToolResult(tool="gmail_client", status="failed")),
                ),
                selected_route=route,
            )
        result = _success(
            "gmail_client",
            ("Gmail API interrogee pour cette demande.", "Reponse construite depuis le module Gmail local."),
            confidence=0.82,
        )
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "cursor_agent_setup":
        result_payload = setup_cursor_agent(auto_install=trusted_actions)
        content = format_cursor_agent_setup_response(result_payload)
        status = "success" if result_payload.get("status") == "ready" else "partial"
        evidence = (
            ("cursor-agent disponible ou installe via WSL.",)
            if status == "success"
            else ("Diagnostic Cursor Agent effectue; installation exploitable absente.",)
        )
        result = ToolResult(
            tool="cursor_agent_setup",
            status=status,
            evidence=evidence,
            data=result_payload,
            error="" if status == "success" else "cursor-agent indisponible apres tentative d'installation.",
            next_actions=(
                "installer ou initialiser WSL",
                "relancer: installe cursor agent",
                "verifier avec cursor-agent --version",
            )
            if status != "success"
            else (),
            confidence=0.88 if status == "success" else 0.64,
        )
        return RouteExecution(
            content=content,
            result=verify_result(result),
            selected_route="cursor_agent_setup",
        )

    if route == "cursor_work" or (use_domain_fallback and understanding.primary_domain == "cursor"):
        content = (
            build_cursor_work_session_response(message)
            if trusted_actions
            else build_chat_cursor_prompt_response(message)
        )
        result = _success(
            "cursor_bridge",
            ("Projet resolu ou prompt Cursor prepare via le module projet.",),
            confidence=0.84,
        )
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "project_factory" or (use_domain_fallback and understanding.primary_domain == "project"):
        if not trusted_actions:
            result = _blocked(
                "project_factory",
                "Project Factory demande une session fiable: PC local ou Telegram autorise.",
                ("relancer depuis le PC local", "ou depuis ton Telegram autorise"),
            )
            return RouteExecution(content=build_blocked_response(result), result=result, selected_route=route)

        bundle = create_project_factory_actions(message)
        plan = bundle["plan"]
        actions = bundle["actions"]
        results = auto_execute_project_factory_actions(actions)
        content = format_project_factory_results(plan, results)
        failed = [result for result in results if isinstance(result.get("action"), dict) and result["action"].get("status") == "failed"]
        skipped = [result for result in results if result.get("skipped")]
        status = "partial" if failed or skipped else "success"
        result = ToolResult(
            tool="project_factory",
            status=status,
            evidence=(
                f"Workspace cible: {plan['workspace_path']}",
                f"Actions Project Factory traitees: {len(results)}",
            ),
            data={"plan": plan, "results": results},
            confidence=0.88 if status == "success" else 0.68,
        )
        return RouteExecution(
            content=content,
            result=verify_result(result),
            selected_route="project_factory",
        )

    if route == "spotify" or (use_domain_fallback and understanding.primary_domain == "spotify"):
        content = open_spotify_from_message(message)
        if not content:
            return RouteExecution(
                content="",
                result=_failed("spotify_assistant", "Spotify n'a pas produit de resultat exploitable."),
                selected_route=route,
            )
        result = _success("spotify_assistant", ("Commande Spotify envoyee au PC local.",), confidence=0.82)
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "desktop_control" or (use_domain_fallback and understanding.primary_domain == "desktop"):
        if wants_screen_navigation(message):
            navigation = await navigate_screen(message)
            content = format_screen_navigation_response(navigation)
            status = "success" if navigation.get("status") in {"done", "partial"} else "partial"
            result = ToolResult(
                tool="screen_navigator",
                status=status,
                evidence=(
                    f"Navigation ecran tentee: {navigation.get('executed_count', 0)} action(s) executee(s).",
                    f"Statut navigation: {navigation.get('status', 'inconnu')}",
                ),
                data={"navigation": navigation},
                confidence=0.8 if status == "success" else 0.58,
            )
            return RouteExecution(content=content, result=verify_result(result), selected_route="screen_read")
        content = execute_desktop_control_from_message(message)
        if not content:
            return RouteExecution(
                content="",
                result=_failed("desktop_automation", "Aucune action PC fiable n'a ete detectee."),
                selected_route=route,
            )
        result = _success("desktop_automation", ("Commande clavier/souris envoyee au PC local.",), confidence=0.78)
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "beeper_messages" or (use_domain_fallback and understanding.primary_domain == "beeper"):
        content = await build_beeper_chat_response(message)
        if not content:
            return RouteExecution(
                content="",
                result=_failed("beeper_assistant", "Beeper n'a pas donne de resultat exploitable."),
                selected_route=route,
            )
        if not beeper_response_has_useful_content(content):
            return RouteExecution(
                content=content,
                result=_failed(
                    "beeper_assistant",
                    "Beeper n'est pas visible ou la lecture pixels n'a pas donne de contenu utile.",
                    ("relire l'ecran courant", "ouvrir Beeper puis recommencer", "essayer une route web si la demande ne concerne pas Beeper"),
                    confidence=0.32,
                ),
                selected_route=route,
            )
        result = _success("beeper_assistant", ("Beeper ouvert/lu via le pont local disponible.",), confidence=0.72)
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "linkedin_activity" or (
        use_domain_fallback
        and understanding.primary_domain == "linkedin"
        and understanding.expected_outcome in {"read", "read_then_summarize", "read_then_open"}
    ):
        content = await build_linkedin_activity_response(message)
        if not content:
            return RouteExecution(
                content="",
                result=_failed("linkedin_activity", "Aucun signal LinkedIn exploitable n'a ete trouve."),
                selected_route=route,
            )
        result = _success(
            "linkedin_activity",
            ("Signaux LinkedIn lus sans publication.", "Aucun brouillon de post prepare."),
            confidence=0.82,
        )
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "linkedin_browser_post" or (use_domain_fallback and understanding.primary_domain == "linkedin"):
        content = await build_linkedin_chat_response(message)
        if not content:
            return RouteExecution(
                content="",
                result=_failed("linkedin_assistant", "LinkedIn assistant n'a pas produit de brouillon exploitable."),
                selected_route=route,
            )
        result = _success(
            "linkedin_assistant",
            ("Post LinkedIn prepare sans publication.", "Ouverture/remplissage navigateur tente."),
            confidence=0.78,
        )
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "screen_read" or (use_domain_fallback and understanding.primary_domain == "screen"):
        if wants_screen_navigation(message):
            navigation = await navigate_screen(message)
            content = format_screen_navigation_response(navigation)
            status = "success" if navigation.get("status") in {"done", "partial"} else "partial"
            result = ToolResult(
                tool="screen_navigator",
                status=status,
                evidence=(
                    f"Navigation ecran tentee: {navigation.get('executed_count', 0)} action(s) executee(s).",
                    f"Statut navigation: {navigation.get('status', 'inconnu')}",
                ),
                data={"navigation": navigation},
                confidence=0.8 if status == "success" else 0.58,
            )
            return RouteExecution(content=content, result=verify_result(result), selected_route="screen_read")
        visual_result = await analyze_visual_action(message, execute=True)
        content = format_visual_action_response(visual_result)
        result = _success("screen_reader", ("Capture ecran analysee avant action visuelle.",), confidence=0.76)
        return RouteExecution(content=content, result=result, selected_route="screen_read")

    if route == "browser_or_video" or (use_domain_fallback and understanding.primary_domain == "browser"):
        if wants_screen_navigation(message):
            navigation = await navigate_screen(message)
            content = format_screen_navigation_response(navigation)
            status = "success" if navigation.get("status") in {"done", "partial"} else "partial"
            result = ToolResult(
                tool="screen_navigator",
                status=status,
                evidence=(
                    f"Navigation navigateur/ecran tentee: {navigation.get('executed_count', 0)} action(s) executee(s).",
                    f"Statut navigation: {navigation.get('status', 'inconnu')}",
                ),
                data={"navigation": navigation},
                confidence=0.8 if status == "success" else 0.58,
            )
            return RouteExecution(content=content, result=verify_result(result), selected_route="screen_read")
        content = open_assisted_browser_from_message(message) or open_browser_from_message(message)
        if not content:
            return RouteExecution(
                content="",
                result=_failed(
                    "browser_assistant",
                    "Aucune destination navigateur fiable n'a ete detectee.",
                    fallback_for_result(ToolResult(tool="browser_assistant", status="failed")),
                ),
                selected_route=route,
            )
        result = _success(
            "browser_assistant",
            ("Brave/navigateur local appele avec une URL interpretee.",),
            confidence=0.8,
        )
        return RouteExecution(content=content, result=result, selected_route=route)

    if route == "web_search" or (use_domain_fallback and understanding.primary_domain == "web"):
        query = detect_web_search_query(message) or message
        web_results = await search_web(query)
        content = format_web_results(query, web_results)
        result = _success("web_search", ("Recherche web effectuee avec resultats formates.",), confidence=0.8)
        return RouteExecution(
            content=content,
            result=result,
            selected_route="web_search",
            requires_action=False,
        )

    return None


def _failure_summary(state: CognitiveState) -> str:
    lines = ["Mode resolution active: aucun resultat final fiable n'est encore prouve."]
    if state.tool_results:
        lines.append("")
        lines.append("Pistes tentees:")
        for result in state.tool_results:
            status = result.status
            detail = result.error or (result.evidence[0] if result.evidence else "aucune preuve")
            lines.append(f"- {result.tool}: {status} - {detail}")
    lines.append("")
    lines.append("Prochaine piste logique: reformuler la recherche web ou passer par un outil local plus specifique.")
    return "\n".join(lines)


async def run_cognitive_loop(
    message: str,
    understanding: UnderstandingFrame,
    trusted_actions: bool,
    channel: str = "web",
) -> CognitiveLoopResult:
    state = CognitiveState(
        goal=goal_frame_from_understanding(understanding),
        channel=channel,
        trusted_actions=trusted_actions,
    )
    route = understanding.action_plan.route

    map_result = await _map_preview(
        message,
        context=understanding.context_focus,
        trusted_actions=trusted_actions,
    )
    if map_result:
        content, tool_result, web_preview = map_result
        state.add_result(tool_result)
        state.handled = True
        critic = criticize_response(content, state.tool_results, requires_action=False)
        if not critic.passed:
            content = build_critic_response(critic)
        selected_route = "map3d" if web_preview and web_preview.get("type") == "map3d" else "map_preview"
        return CognitiveLoopResult(
            handled=True,
            message=_assistant_payload(content, understanding, state, selected_route, web_preview=web_preview),
            state=state,
            critic=critic_report_to_dict(critic),
        )

    supported_domains = {"browser", "cursor", "gmail", "spotify", "desktop", "beeper", "web", "linkedin", "screen"}
    if route not in ACTION_ROUTES and understanding.primary_domain not in supported_domains:
        return CognitiveLoopResult(handled=False, state=state)

    last_route = route
    last_critic = None
    route_queue = _route_sequence(str(route), understanding)
    attempted_routes: set[str] = set()
    max_attempts = _max_reasoning_attempts()

    while route_queue and len(attempted_routes) < max_attempts:
        candidate_route = route_queue.pop(0)
        if candidate_route in attempted_routes:
            continue
        attempted_routes.add(candidate_route)
        last_route = candidate_route
        try:
            execution = await _execute_route_once(
                message,
                understanding,
                candidate_route,
                trusted_actions=trusted_actions,
            )
        except Exception as exc:  # noqa: BLE001 - every tool failure becomes a retryable result.
            failed = ToolResult(tool=_tool_for_route(candidate_route, understanding), status="failed", error=str(exc))
            result = _failed(
                failed.tool,
                str(exc),
                fallback_for_result(failed),
            )
            state.add_result(result)
            if settings.eva_problem_solver_enabled:
                for fallback_route in problem_routes_for_result(result, understanding, trusted_actions):
                    if fallback_route not in attempted_routes and fallback_route not in route_queue:
                        route_queue.append(fallback_route)
            continue

        if not execution:
            result = _failed(
                _tool_for_route(candidate_route, understanding),
                "Route non executable par les outils locaux actuels.",
                ("essayer une autre route cognitive",),
                confidence=0.25,
            )
            state.add_result(result)
            if settings.eva_problem_solver_enabled:
                for fallback_route in problem_routes_for_result(result, understanding, trusted_actions):
                    if fallback_route not in attempted_routes and fallback_route not in route_queue:
                        route_queue.append(fallback_route)
            continue

        state.add_result(execution.result)
        if not execution.content or not execution.result.ok:
            if settings.eva_problem_solver_enabled:
                for fallback_route in problem_routes_for_result(execution.result, understanding, trusted_actions):
                    if fallback_route not in attempted_routes and fallback_route not in route_queue:
                        route_queue.append(fallback_route)
            continue

        state.handled = True
        critic = criticize_response(
            execution.content,
            state.tool_results,
            requires_action=execution.requires_action,
        )
        last_critic = critic
        if critic.passed:
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(
                    execution.content,
                    understanding,
                    state,
                    execution.selected_route,
                    web_preview=execution.web_preview,
                ),
                state=state,
                critic=critic_report_to_dict(critic),
            )

        if not critic.retryable:
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(build_critic_response(critic), understanding, state, execution.selected_route),
                state=state,
                critic=critic_report_to_dict(critic),
            )

    if state.tool_results:
        state.handled = True
        latest_result = state.tool_results[-1]
        resolution = diagnose_problem(latest_result, understanding, trusted_actions)
        content = (
            build_problem_solver_response(message, state, resolution)
            if settings.eva_problem_solver_enabled
            else _failure_summary(state)
        )
        return CognitiveLoopResult(
            handled=True,
            message=_assistant_payload(content, understanding, state, last_route),
            state=state,
            critic=critic_report_to_dict(last_critic) if last_critic else None,
        )

    return CognitiveLoopResult(handled=False, state=state)

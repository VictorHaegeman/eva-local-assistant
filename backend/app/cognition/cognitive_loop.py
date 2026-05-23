from dataclasses import dataclass
from typing import Any

from app.agents.understanding import UnderstandingFrame
from app.cognition.critic import critic_report_to_dict, criticize_response
from app.cognition.response_builder import build_blocked_response, build_critic_response
from app.cognition.retry_policy import fallback_for_result
from app.cognition.state import (
    CognitiveState,
    cognitive_state_to_dict,
    goal_frame_from_understanding,
)
from app.cognition.tool_result import ToolResult, tool_result_to_dict
from app.cognition.verifier import verify_result
from app.integrations.beeper_assistant import build_beeper_chat_response
from app.integrations.browser_actions import open_browser_from_message
from app.integrations.browser_assistant import open_assisted_browser_from_message
from app.integrations.browser import open_url
from app.integrations.desktop_chat import execute_desktop_control_from_message
from app.integrations.gmail_chat import build_gmail_chat_response
from app.integrations.map_preview import build_map_preview_from_message
from app.integrations.spotify_assistant import open_spotify_from_message
from app.projects.project_chat import (
    build_chat_cursor_prompt_response,
    build_cursor_work_session_response,
)
from app.screen.visual_action import analyze_visual_action, format_visual_action_response
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


ACTION_ROUTES = {
    "browser_or_video",
    "cursor_work",
    "gmail_read",
    "gmail_reply_audit",
    "gmail_reply_draft",
    "spotify",
    "desktop_control",
    "beeper_messages",
    "web_search",
}


ROUTE_LABELS = {
    "map_preview": "Carte integree",
    "map3d": "Vue 3D",
    "web_search": "Recherche web",
    "browser_or_video": "Navigateur",
    "cursor_work": "Projet / Cursor",
    "gmail_read": "Gmail lecture",
    "gmail_reply_audit": "Audit reponses",
    "gmail_reply_draft": "Brouillon Gmail",
    "spotify": "Spotify",
    "desktop_control": "Controle PC",
    "beeper_messages": "Beeper",
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
    return route in {"browser_or_video", "cursor_work", "spotify", "desktop_control", "beeper_messages"}


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
    elif domain in {"cursor", "project"} or selected_route == "cursor_work":
        base_options.extend(["cursor_work", "web_search", "generic_chat"])
    elif domain == "browser":
        base_options.extend(["browser_or_video", "web_search", "generic_chat"])
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

    return {
        "title": "Eva pipeline",
        "summary": state.goal.goal,
        "selected": selected_label,
        "confidence": round(max(0.0, min(1.0, confidence)) * 100),
        "status": status,
        "stages": [
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
        ],
        "evidence": evidence,
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

    if route not in ACTION_ROUTES and understanding.primary_domain not in {"browser", "cursor", "gmail", "spotify", "desktop", "beeper", "web"}:
        return CognitiveLoopResult(handled=False, state=state)

    if _requires_trusted(route) and not trusted_actions:
        result = _blocked(
            understanding.tool_preference,
            "Cette action locale demande une session fiable: PC local ou Telegram autorise.",
            ("refaire la demande depuis le PC local", "ou utiliser ton Telegram autorise"),
        )
        state.add_result(result)
        state.handled = True
        return CognitiveLoopResult(
            handled=True,
            message=_assistant_payload(
                build_blocked_response(result),
                understanding,
                state,
                route,
            ),
            state=state,
        )

    try:
        if route in {"gmail_read", "gmail_reply_audit", "gmail_reply_draft"} or understanding.primary_domain == "gmail":
            content = await build_gmail_chat_response(message, force_list=route == "gmail_read")
            if not content:
                return CognitiveLoopResult(handled=False, state=state)
            result = _success(
                "gmail_client",
                ("Gmail API interrogee pour cette demande.", "Reponse construite depuis le module Gmail local."),
                confidence=0.82,
            )
            state.add_result(result)
            state.handled = True
            critic = criticize_response(content, state.tool_results, requires_action=True)
            if not critic.passed:
                content = build_critic_response(critic)
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
                critic=critic_report_to_dict(critic),
            )

        if route == "cursor_work" or understanding.primary_domain == "cursor":
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
            state.add_result(result)
            state.handled = True
            critic = criticize_response(content, state.tool_results, requires_action=True)
            if not critic.passed:
                result = ToolResult(
                    tool="cursor_bridge",
                    status="partial",
                    evidence=result.evidence,
                    next_actions=fallback_for_result(result),
                    confidence=0.68,
                )
                state.add_result(result)
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
                critic=critic_report_to_dict(critic),
            )

        if route == "spotify" or understanding.primary_domain == "spotify":
            content = open_spotify_from_message(message)
            if not content:
                return CognitiveLoopResult(handled=False, state=state)
            result = _success("spotify_assistant", ("Commande Spotify envoyee au PC local.",), confidence=0.82)
            state.add_result(result)
            state.handled = True
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
            )

        if route == "desktop_control" or understanding.primary_domain == "desktop":
            content = execute_desktop_control_from_message(message)
            if not content:
                return CognitiveLoopResult(handled=False, state=state)
            result = _success("desktop_automation", ("Commande clavier/souris envoyee au PC local.",), confidence=0.78)
            state.add_result(result)
            state.handled = True
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
            )

        if route == "beeper_messages" or understanding.primary_domain == "beeper":
            content = await build_beeper_chat_response(message)
            if not content:
                return CognitiveLoopResult(handled=False, state=state)
            result = _success("beeper_assistant", ("Beeper ouvert/lu via le pont local disponible.",), confidence=0.72)
            state.add_result(result)
            state.handled = True
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
            )

        if understanding.primary_domain == "screen":
            visual_result = await analyze_visual_action(message, execute=True)
            content = format_visual_action_response(visual_result)
            result = _success("screen_reader", ("Capture ecran analysee avant action visuelle.",), confidence=0.76)
            state.add_result(result)
            state.handled = True
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, "screen_read"),
                state=state,
            )

        if route == "browser_or_video" or understanding.primary_domain == "browser":
            content = open_assisted_browser_from_message(message) or open_browser_from_message(message)
            if not content:
                return CognitiveLoopResult(handled=False, state=state)
            result = _success("browser_assistant", ("Brave/navigateur local appele avec une URL interpretee.",), confidence=0.8)
            state.add_result(result)
            state.handled = True
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
            )

        if route == "web_search" or understanding.primary_domain == "web":
            query = detect_web_search_query(message) or message
            web_results = await search_web(query)
            content = format_web_results(query, web_results)
            result = _success("web_search", ("Recherche web effectuee avec resultats formates.",), confidence=0.8)
            state.add_result(result)
            state.handled = True
            return CognitiveLoopResult(
                handled=True,
                message=_assistant_payload(content, understanding, state, route),
                state=state,
            )
    except Exception as exc:  # noqa: BLE001 - normalize tool failures for the loop.
        result = ToolResult(
            tool=understanding.tool_preference,
            status="failed",
            error=str(exc),
            next_actions=fallback_for_result(
                ToolResult(tool=understanding.tool_preference, status="failed", error=str(exc))
            ),
            confidence=0.35,
        )
        state.add_result(result)
        state.handled = True
        return CognitiveLoopResult(
            handled=True,
            message=_assistant_payload(build_blocked_response(result), understanding, state, route),
            state=state,
        )

    return CognitiveLoopResult(handled=False, state=state)

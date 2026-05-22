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


async def _map_preview(message: str) -> tuple[str, ToolResult, dict[str, Any] | None] | None:
    preview = await build_map_preview_from_message(message)
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

    result = _success(
        "map_preview",
        (
            f"Carte integree preparee via {web_preview.get('provider', 'OpenStreetMap')}",
            f"URL embed verifiee: {web_preview.get('embed_url')}",
        ),
        data={"web_preview": web_preview},
        confidence=0.92,
    )
    return str(preview["content"]), result, web_preview


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

    map_result = await _map_preview(message)
    if map_result:
        content, tool_result, web_preview = map_result
        state.add_result(tool_result)
        state.handled = True
        critic = criticize_response(content, state.tool_results, requires_action=False)
        if not critic.passed:
            content = build_critic_response(critic)
        payload: dict[str, Any] = {
            "role": "assistant",
            "content": content,
        }
        if web_preview:
            payload["web_preview"] = web_preview
        return CognitiveLoopResult(
            handled=True,
            message=payload,
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
            message={"role": "assistant", "content": build_blocked_response(result)},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
                message={"role": "assistant", "content": content},
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
            message={"role": "assistant", "content": build_blocked_response(result)},
            state=state,
        )

    return CognitiveLoopResult(handled=False, state=state)

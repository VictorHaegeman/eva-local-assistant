from dataclasses import dataclass, field
from typing import Any

from app.agents.understanding import UnderstandingFrame
from app.cognition.tool_result import ToolResult


@dataclass(frozen=True)
class GoalFrame:
    raw_message: str
    goal: str
    domain: str
    expected_outcome: str
    target_hint: str
    success_criteria: tuple[str, ...]
    confidence: float


@dataclass
class CognitiveState:
    goal: GoalFrame
    channel: str = "web"
    trusted_actions: bool = False
    tool_results: list[ToolResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    handled: bool = False

    def add_result(self, result: ToolResult) -> None:
        self.tool_results.append(result)


def goal_frame_from_understanding(frame: UnderstandingFrame) -> GoalFrame:
    return GoalFrame(
        raw_message=frame.raw_message,
        goal=frame.interpreted_goal,
        domain=frame.primary_domain,
        expected_outcome=frame.expected_outcome,
        target_hint=frame.context_focus or frame.raw_message,
        success_criteria=tuple(frame.required_evidence),
        confidence=frame.intent.confidence,
    )


def cognitive_state_to_dict(state: CognitiveState) -> dict[str, Any]:
    return {
        "goal": {
            "raw_message": state.goal.raw_message,
            "goal": state.goal.goal,
            "domain": state.goal.domain,
            "expected_outcome": state.goal.expected_outcome,
            "target_hint": state.goal.target_hint,
            "success_criteria": list(state.goal.success_criteria),
            "confidence": state.goal.confidence,
        },
        "channel": state.channel,
        "trusted_actions": state.trusted_actions,
        "handled": state.handled,
        "notes": list(state.notes),
        "tool_results": [
            {
                "tool": result.tool,
                "status": result.status,
                "evidence": list(result.evidence),
                "data": result.data,
                "next_actions": list(result.next_actions),
                "error": result.error,
                "confidence": result.confidence,
            }
            for result in state.tool_results
        ],
    }

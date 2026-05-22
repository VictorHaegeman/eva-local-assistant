from dataclasses import dataclass, field
from typing import Any, Literal


ToolStatus = Literal["success", "partial", "failed", "blocked", "skipped"]


@dataclass(frozen=True)
class ToolResult:
    tool: str
    status: ToolStatus
    evidence: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    next_actions: tuple[str, ...] = ()
    error: str = ""
    confidence: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in {"success", "partial"} and bool(self.evidence)


def tool_result_to_dict(result: ToolResult) -> dict[str, Any]:
    return {
        "tool": result.tool,
        "status": result.status,
        "evidence": list(result.evidence),
        "data": result.data,
        "next_actions": list(result.next_actions),
        "error": result.error,
        "confidence": result.confidence,
    }

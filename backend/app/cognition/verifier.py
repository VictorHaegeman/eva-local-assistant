from app.cognition.tool_result import ToolResult


def has_evidence(result: ToolResult) -> bool:
    return bool(result.evidence) and result.status in {"success", "partial"}


def verify_result(result: ToolResult, required_evidence: tuple[str, ...] = ()) -> ToolResult:
    if result.status in {"blocked", "failed"}:
        return result

    if has_evidence(result):
        return result

    return ToolResult(
        tool=result.tool,
        status="failed",
        evidence=(),
        data=result.data,
        next_actions=result.next_actions,
        error=(
            result.error
            or "Action non verifiee: l'outil n'a pas fourni de preuve locale exploitable."
        ),
        confidence=min(result.confidence, 0.35),
    )


def verified_any(results: list[ToolResult]) -> bool:
    return any(has_evidence(result) for result in results)

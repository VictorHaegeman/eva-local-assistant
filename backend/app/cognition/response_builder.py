from app.cognition.critic import CriticReport
from app.cognition.tool_result import ToolResult


def _evidence_lines(result: ToolResult) -> list[str]:
    return [f"- {evidence}" for evidence in result.evidence[:5]]


def build_blocked_response(result: ToolResult) -> str:
    lines = [
        "Je ne l'execute pas encore.",
        f"Raison: {result.error or 'action bloquee par la politique locale.'}",
    ]
    if result.next_actions:
        lines.append("")
        lines.append("Prochaine action utile:")
        lines.extend(f"- {action}" for action in result.next_actions)
    return "\n".join(lines)


def build_verified_response(content: str, result: ToolResult | None = None) -> str:
    if not result or not result.evidence:
        return content

    evidence = "\n".join(_evidence_lines(result))
    return f"{content}\n\nPreuves locales:\n{evidence}"


def build_critic_response(report: CriticReport) -> str:
    lines = [
        "Je bloque ma reponse initiale parce qu'elle n'etait pas assez verifiee.",
        f"Diagnostic: {report.reason}",
    ]
    if report.fix:
        lines.append(f"Correction a appliquer: {report.fix}")
    return "\n".join(lines)

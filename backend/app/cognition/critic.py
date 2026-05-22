from dataclasses import dataclass

from app.cognition.tool_result import ToolResult
from app.cognition.verifier import verified_any


WEAK_ENDINGS = (
    "dis-moi si tu veux autre chose",
    "dites-moi si vous souhaitez autre chose",
    "pouvez-vous me dire si vous souhaitez que je fasse quelque chose d'autre",
    "souhaitez-vous que je fasse quelque chose d'autre",
)

UNPROVEN_ACTION_CLAIMS = (
    "j'ai ouvert",
    "j ai ouvert",
    "j'ai lance",
    "j ai lance",
    "j'ai charge",
    "j ai charge",
    "je vais maintenant ouvrir",
)


@dataclass(frozen=True)
class CriticReport:
    passed: bool
    severity: str = "ok"
    reason: str = ""
    fix: str = ""
    retryable: bool = False


def criticize_response(
    response: str,
    tool_results: list[ToolResult],
    requires_action: bool = False,
) -> CriticReport:
    normalized = " ".join(response.lower().split())

    if any(marker in normalized for marker in WEAK_ENDINGS):
        return CriticReport(
            passed=False,
            severity="medium",
            reason="Reponse trop passive avec question generique.",
            fix="Remplacer par l'action suivante logique ou un statut factuel.",
            retryable=False,
        )

    has_tool_evidence = verified_any(tool_results)
    if any(marker in normalized for marker in UNPROVEN_ACTION_CLAIMS) and not has_tool_evidence:
        return CriticReport(
            passed=False,
            severity="high",
            reason="La reponse pretend avoir execute une action sans preuve outil.",
            fix="Bloquer la formulation ou relancer l'outil adapte.",
            retryable=True,
        )

    if requires_action and not has_tool_evidence:
        return CriticReport(
            passed=False,
            severity="high",
            reason="La demande necessitait une action mais aucun resultat verifie n'existe.",
            fix="Executer un outil local ou expliquer le blocage precis.",
            retryable=True,
        )

    return CriticReport(passed=True)


def critic_report_to_dict(report: CriticReport) -> dict[str, object]:
    return {
        "passed": report.passed,
        "severity": report.severity,
        "reason": report.reason,
        "fix": report.fix,
        "retryable": report.retryable,
    }

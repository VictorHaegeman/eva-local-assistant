"""Boardroom — orchestration CEO -> CTO -> CFO -> décision.

Chaque demande de réflexion passe par les officiers concernés. Le board produit une
délibération (contexte pour la réponse finale), une note de confirmation si le CFO
l'exige, et une trace affichable. Les décisions sont journalisées dans Obsidian.
"""

from dataclasses import dataclass, field
from typing import Any

from app.board.ceo import CeoBrief, deliberate_ceo
from app.board.cfo import CfoVerdict, deliberate_cfo
from app.board.coo import CooPlan, deliberate_coo
from app.board.cto import CtoPlan, deliberate_cto
from app.config import settings
from app.llm.brain import resolve_provider
from app.memory.obsidian_store import append_board_decision


@dataclass
class BoardDeliberation:
    objective: str
    direct_answer: str = ""
    deliberation_context: str = ""
    requires_confirmation: bool = False
    confirmation_note: str = ""
    officers_summary: str = ""
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def is_direct(self) -> bool:
        return bool(self.direct_answer.strip())


def board_enabled() -> bool:
    """Le board n'est utile qu'avec un cerveau capable (Groq) sauf forçage explicite."""
    raw = str(getattr(settings, "eva_board_enabled", "auto")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    # auto: actif seulement si le cerveau effectif est Groq (multi-appels rapides).
    return resolve_provider() == "groq"


_RISK_STATUS = {"faible": "done", "moyen": "partial", "eleve": "blocked"}


def _ceo_stage(ceo: CeoBrief) -> dict[str, Any]:
    return {
        "key": "ceo",
        "label": "CEO",
        "status": "done",
        "detail": f"{ceo.objective} ({ceo.complexity})",
    }


def _cto_stage(cto: CtoPlan) -> dict[str, Any]:
    detail = cto.approach or "Plan technique"
    if cto.blocker:
        detail = f"{detail} — blocage: {cto.blocker}"
    return {
        "key": "cto",
        "label": "CTO",
        "status": _RISK_STATUS.get(cto.technical_risk, "done") if cto.feasible else "blocked",
        "detail": detail,
    }


def _cfo_stage(cfo: CfoVerdict) -> dict[str, Any]:
    status = "done" if cfo.verdict == "go" else ("partial" if cfo.verdict == "prudence" else "blocked")
    detail = f"verdict={cfo.verdict}, risque={cfo.risk_level}"
    if cfo.reason:
        detail = f"{detail} — {cfo.reason}"
    return {"key": "cfo", "label": "CFO", "status": status, "detail": detail}


def _coo_stage(coo: CooPlan) -> dict[str, Any]:
    detail = coo.next_action or "Prochaine action"
    if coo.owner:
        detail = f"{detail} ({coo.owner})"
    return {
        "key": "coo",
        "label": "COO",
        "status": "done" if coo.execute_now else "ready",
        "detail": detail,
    }


def _build_context(
    ceo: CeoBrief,
    cto: CtoPlan | None,
    cfo: CfoVerdict | None,
    coo: "CooPlan | None" = None,
) -> str:
    lines = [
        "Deliberation du board interne d'Eva (a respecter pour la reponse finale):",
        f"- CEO / objectif: {ceo.objective}",
    ]
    if ceo.rationale:
        lines.append(f"- CEO / raison: {ceo.rationale}")
    if cto:
        lines.append(f"- CTO / approche: {cto.approach or 'n/a'}")
        if cto.steps:
            lines.append("- CTO / etapes: " + " | ".join(cto.steps))
        if cto.tools:
            lines.append("- CTO / outils: " + ", ".join(cto.tools))
        lines.append(f"- CTO / faisabilite: {'oui' if cto.feasible else 'non'}, risque {cto.technical_risk}")
        if cto.blocker:
            lines.append(f"- CTO / blocage: {cto.blocker}")
    if cfo:
        lines.append(
            f"- CFO / verdict: {cfo.verdict} (risque {cfo.risk_level}, "
            f"{'reversible' if cfo.reversible else 'irreversible'})"
        )
        if cfo.cost:
            lines.append(f"- CFO / cout: {cfo.cost}")
        if cfo.reason:
            lines.append(f"- CFO / raison: {cfo.reason}")
    if coo:
        lines.append(f"- COO / prochaine action: {coo.next_action or 'n/a'}")
        if coo.sequence:
            lines.append("- COO / sequence: " + " -> ".join(coo.sequence))
        if coo.owner:
            lines.append(f"- COO / execute: {coo.owner} ({'maintenant' if coo.execute_now else 'apres validation'})")
        if coo.follow_up:
            lines.append(f"- COO / verification: {coo.follow_up}")
    lines.append(
        "Synthetise comme le CEO: reponse claire + prochaine action concrete (celle du COO). "
        "Si le CFO impose une validation ou bloque, annonce-le sans pretendre l'action faite."
    )
    return "\n".join(lines)


def _officers_summary(
    ceo: CeoBrief,
    cto: CtoPlan | None,
    cfo: CfoVerdict | None,
    coo: "CooPlan | None" = None,
) -> str:
    parts = [f"CEO={ceo.complexity}"]
    if cto:
        parts.append(f"CTO={'faisable' if cto.feasible else 'bloque'}/{cto.technical_risk}")
    if cfo:
        parts.append(f"CFO={cfo.verdict}/{cfo.risk_level}")
    if coo:
        parts.append(f"COO={'execute' if coo.execute_now else 'prepare'}")
    return ", ".join(parts)


async def run_board_deliberation(
    message: str,
    conversation_summary: str = "",
    trusted_actions: bool = False,
) -> BoardDeliberation:
    ceo = await deliberate_ceo(message, conversation_summary=conversation_summary)

    base_trace: dict[str, Any] = {
        "title": "Conseil Eva (CEO / CTO / CFO)",
        "summary": ceo.objective,
        "selected": "Board",
        "status": "done",
        "confidence": 80,
        "evidence": [],
        "attempts": [],
        "memory": {"summary": "", "clusters": [], "count": 0},
        "skills": {"summary": "", "keys": []},
    }

    if ceo.is_trivial:
        trace = {**base_trace, "stages": [_ceo_stage(ceo)]}
        append_board_decision(ceo.objective, ceo.direct_answer, "CEO=trivial")
        return BoardDeliberation(
            objective=ceo.objective,
            direct_answer=ceo.direct_answer,
            officers_summary="CEO=trivial",
            trace=trace,
        )

    cto = await deliberate_cto(ceo.objective, message) if ceo.needs_cto else None
    cto_summary = ""
    if cto:
        cto_summary = cto.approach + (f" | etapes: {' | '.join(cto.steps)}" if cto.steps else "")
    cfo = await deliberate_cfo(ceo.objective, message, cto_summary=cto_summary) if ceo.needs_cfo else None

    requires_confirmation = bool(cfo and (cfo.requires_confirmation or cfo.blocks))

    coo = None
    if ceo.needs_coo and not (cfo and cfo.blocks):
        coo = await deliberate_coo(
            ceo.objective,
            message,
            plan_summary=cto_summary,
            cfo_clearance=not requires_confirmation,
        )

    stages = [_ceo_stage(ceo)]
    if cto:
        stages.append(_cto_stage(cto))
    if cfo:
        stages.append(_cfo_stage(cfo))
    if coo:
        stages.append(_coo_stage(coo))
    confirmation_note = ""
    if cfo and cfo.blocks:
        confirmation_note = (
            f"⚠️ Le CFO bloque cette action (risque {cfo.risk_level}): "
            f"{cfo.reason or 'action critique non validee'}. Je prepare le plan sans l'executer."
        )
    elif requires_confirmation:
        confirmation_note = (
            f"⚠️ Le CFO demande ta validation avant d'agir (risque {cfo.risk_level}): "
            f"{cfo.reason or 'action sensible'}."
        )

    deliberation_context = _build_context(ceo, cto, cfo, coo)
    officers_summary = _officers_summary(ceo, cto, cfo, coo)
    append_board_decision(ceo.objective, confirmation_note or "deliberation board", officers_summary)

    return BoardDeliberation(
        objective=ceo.objective,
        deliberation_context=deliberation_context,
        requires_confirmation=requires_confirmation,
        confirmation_note=confirmation_note,
        officers_summary=officers_summary,
        trace={**base_trace, "stages": stages, "status": "partial" if requires_confirmation else "done"},
    )

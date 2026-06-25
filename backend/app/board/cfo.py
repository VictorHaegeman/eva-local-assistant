"""CFO — Coût, risque, ressources et garde-fou du board Eva."""

from dataclasses import dataclass

from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.memory.obsidian_store import ObsidianMemoryError, build_board_officer_context


CFO_SYSTEM_PROMPT = (
    "Tu es le CFO du conseil interne d'Eva. Tu evalues le cout (temps, argent, tokens), "
    "le risque et l'irreversibilite d'une action, et tu es le garde-fou avant toute action "
    "critique (envoyer, publier, supprimer, push, depenser, utiliser un compte externe). "
    "Tu gardes Eva gratuite: pas de dependance payante obligatoire. "
    "Reponds UNIQUEMENT en JSON avec: "
    "verdict (string: 'go' | 'prudence' | 'bloquer'), "
    "risk_level (string: 'faible' | 'moyen' | 'eleve'), "
    "reversible (bool), "
    "requires_confirmation (bool: faut-il une validation humaine explicite), "
    "cost (string: cout estime en 1 phrase), "
    "reason (string: justification courte)."
)


@dataclass(frozen=True)
class CfoVerdict:
    verdict: str = "go"
    risk_level: str = "faible"
    reversible: bool = True
    requires_confirmation: bool = False
    cost: str = ""
    reason: str = ""

    @property
    def blocks(self) -> bool:
        return self.verdict == "bloquer"


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "oui", "vrai"}
    return default


async def deliberate_cfo(objective: str, message: str, cto_summary: str = "") -> CfoVerdict:
    try:
        board_context = build_board_officer_context("cfo", message)
    except ObsidianMemoryError:
        board_context = ""

    user_prompt = (
        (f"{board_context}\n\n" if board_context else "")
        + f"Objectif:\n{objective}\n\n"
        + (f"Plan technique du CTO:\n{cto_summary}\n\n" if cto_summary else "")
        + f"Demande brute de Victor:\n{message}\n\nRends le JSON du CFO."
    )

    try:
        payload = await ask_ollama_json(CFO_SYSTEM_PROMPT, user_prompt, temperature=0.1)
    except OllamaClientError:
        # Repli prudent: on demande validation plutot que d'autoriser aveuglement.
        return CfoVerdict(
            verdict="prudence",
            risk_level="moyen",
            reversible=True,
            requires_confirmation=True,
            cost="indetermine",
            reason="CFO indisponible: validation humaine recommandee par prudence.",
        )

    verdict = str(payload.get("verdict", "go")).strip().lower()
    if verdict not in {"go", "prudence", "bloquer"}:
        verdict = "prudence"
    risk = str(payload.get("risk_level", "faible")).strip().lower()
    if risk not in {"faible", "moyen", "eleve"}:
        risk = "faible"

    return CfoVerdict(
        verdict=verdict,
        risk_level=risk,
        reversible=_as_bool(payload.get("reversible"), default=True),
        requires_confirmation=_as_bool(payload.get("requires_confirmation"), default=verdict != "go"),
        cost=str(payload.get("cost", "")).strip(),
        reason=str(payload.get("reason", "")).strip(),
    )

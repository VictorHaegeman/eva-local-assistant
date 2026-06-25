"""CTO — Faisabilité, technique et plan d'exécution du board Eva."""

from dataclasses import dataclass, field

from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.memory.obsidian_store import ObsidianMemoryError, build_board_officer_context


CTO_SYSTEM_PROMPT = (
    "Tu es le CTO du conseil interne d'Eva. Tu decides COMMENT atteindre l'objectif "
    "avec les outils locaux d'Eva (Brave/navigateur, Gmail, lecture d'ecran, controle PC, "
    "projets/Cursor, recherche web gratuite, fichiers locaux autorises). "
    "Tu raisonnes comme un senior engineer: petites etapes verifiables. "
    "Reponds UNIQUEMENT en JSON avec: "
    "approach (string: l'approche en 1-2 phrases), "
    "steps (array de strings: 2 a 5 etapes concretes), "
    "tools (array de strings: outils locaux pertinents), "
    "feasible (bool: faisable avec les outils locaux), "
    "technical_risk (string: 'faible' | 'moyen' | 'eleve'), "
    "blocker (string: principal point de blocage technique, ou chaine vide)."
)


@dataclass(frozen=True)
class CtoPlan:
    approach: str
    steps: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    feasible: bool = True
    technical_risk: str = "faible"
    blocker: str = ""


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "oui", "vrai"}
    return default


def _as_str_tuple(value: object, limit: int = 5) -> tuple[str, ...]:
    if isinstance(value, list):
        items = [" ".join(str(item).split()) for item in value if str(item).strip()]
        return tuple(items[:limit])
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


async def deliberate_cto(objective: str, message: str) -> CtoPlan:
    try:
        board_context = build_board_officer_context("cto", message)
    except ObsidianMemoryError:
        board_context = ""

    user_prompt = (
        (f"{board_context}\n\n" if board_context else "")
        + f"Objectif fixe par le CEO:\n{objective}\n\n"
        + f"Demande brute de Victor:\n{message}\n\nRends le JSON du CTO."
    )

    try:
        payload = await ask_ollama_json(CTO_SYSTEM_PROMPT, user_prompt, temperature=0.1)
    except OllamaClientError:
        return CtoPlan(
            approach="Plan technique indisponible (cerveau injoignable); proceder prudemment etape par etape.",
            feasible=True,
            technical_risk="moyen",
        )

    risk = str(payload.get("technical_risk", "faible")).strip().lower()
    if risk not in {"faible", "moyen", "eleve"}:
        risk = "faible"

    return CtoPlan(
        approach=str(payload.get("approach", "")).strip(),
        steps=_as_str_tuple(payload.get("steps")),
        tools=_as_str_tuple(payload.get("tools")),
        feasible=_as_bool(payload.get("feasible"), default=True),
        technical_risk=risk,
        blocker=str(payload.get("blocker", "")).strip(),
    )

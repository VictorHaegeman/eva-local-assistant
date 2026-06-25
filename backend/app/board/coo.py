"""COO — Opérations et exécution: ferme la boucle du board Eva.

Le COO transforme la décision (objectif CEO + plan CTO + feu vert CFO) en une
prochaine action concrète et un séquencement, et indique s'il faut exécuter
maintenant ou mettre en file. Il ne contourne jamais le CFO ni la politique de
sécurité: si le CFO bloque ou demande validation, le COO prépare sans exécuter.
"""

from dataclasses import dataclass

from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.memory.obsidian_store import ObsidianMemoryError, build_board_officer_context


COO_SYSTEM_PROMPT = (
    "Tu es le COO du conseil interne d'Eva. Tu fermes la boucle: tu transformes la "
    "decision du board en une prochaine action concrete et un sequencement clair. "
    "Tu ne contournes jamais le CFO: si une validation est requise, tu prepares sans executer. "
    "Reponds UNIQUEMENT en JSON avec: "
    "next_action (string: la prochaine action concrete et unique), "
    "sequence (array de strings: l'ordre des etapes operationnelles), "
    "execute_now (bool: peut-on lancer maintenant sans validation), "
    "owner (string: quel outil/role local execute), "
    "follow_up (string: comment verifier que c'est fait, ou chaine vide)."
)


@dataclass(frozen=True)
class CooPlan:
    next_action: str = ""
    sequence: tuple[str, ...] = ()
    execute_now: bool = False
    owner: str = ""
    follow_up: str = ""


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "oui", "vrai"}
    return default


def _as_str_tuple(value: object, limit: int = 6) -> tuple[str, ...]:
    if isinstance(value, list):
        items = [" ".join(str(item).split()) for item in value if str(item).strip()]
        return tuple(items[:limit])
    if isinstance(value, str) and value.strip():
        return (value.strip(),)
    return ()


async def deliberate_coo(
    objective: str,
    message: str,
    plan_summary: str = "",
    cfo_clearance: bool = True,
) -> CooPlan:
    try:
        board_context = build_board_officer_context("coo", message)
    except ObsidianMemoryError:
        board_context = ""

    clearance_line = (
        "Le CFO autorise l'execution." if cfo_clearance else "Le CFO exige une validation: NE PAS executer, preparer seulement."
    )
    user_prompt = (
        (f"{board_context}\n\n" if board_context else "")
        + f"Objectif:\n{objective}\n\n"
        + (f"Plan du board:\n{plan_summary}\n\n" if plan_summary else "")
        + f"{clearance_line}\n\n"
        + f"Demande brute de Victor:\n{message}\n\nRends le JSON du COO."
    )

    try:
        payload = await ask_ollama_json(COO_SYSTEM_PROMPT, user_prompt, temperature=0.1)
    except OllamaClientError:
        return CooPlan(
            next_action="Preparer la prochaine etape manuellement (cerveau injoignable).",
            execute_now=False,
        )

    return CooPlan(
        next_action=str(payload.get("next_action", "")).strip(),
        sequence=_as_str_tuple(payload.get("sequence")),
        # Sécurité: jamais d'exécution si le CFO n'a pas donné le feu vert.
        execute_now=cfo_clearance and _as_bool(payload.get("execute_now"), default=False),
        owner=str(payload.get("owner", "")).strip(),
        follow_up=str(payload.get("follow_up", "")).strip(),
    )

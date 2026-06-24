"""CEO — Orchestrateur et décision finale du board Eva."""

from dataclasses import dataclass, field

from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.memory.obsidian_store import ObsidianMemoryError, build_board_officer_context


CEO_SYSTEM_PROMPT = (
    "Tu es le CEO du conseil interne d'Eva, l'assistante de Victor. "
    "Ton role: clarifier l'objectif reel, decider quels officiers consulter, et fixer "
    "le critere de reussite. Tu ne codes pas et tu n'executes rien toi-meme. "
    "Reponds UNIQUEMENT en JSON avec ces cles: "
    "objective (string, l'objectif reel reformule), "
    "complexity (string: 'trivial' | 'standard' | 'complexe'), "
    "needs_cto (bool: faut-il l'avis technique/faisabilite), "
    "needs_cfo (bool: faut-il evaluer cout/risque/irreversibilite), "
    "needs_coo (bool: faut-il un plan d'execution concret/sequencement), "
    "direct_answer (string: si trivial, la reponse courte; sinon chaine vide), "
    "rationale (string: 1 phrase). "
    "Mets needs_cfo a true des qu'une action peut envoyer, publier, supprimer, depenser "
    "ou toucher un compte externe."
)


@dataclass(frozen=True)
class CeoBrief:
    objective: str
    complexity: str
    needs_cto: bool
    needs_cfo: bool
    direct_answer: str
    needs_coo: bool = False
    rationale: str = ""

    @property
    def is_trivial(self) -> bool:
        return self.complexity == "trivial" and bool(self.direct_answer.strip())


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "oui", "vrai"}
    return default


async def deliberate_ceo(message: str, conversation_summary: str = "") -> CeoBrief:
    try:
        board_context = build_board_officer_context("ceo", message)
    except ObsidianMemoryError:
        board_context = ""

    user_prompt = (
        f"{board_context}\n\n" if board_context else ""
    ) + (
        f"Contexte recent:\n{conversation_summary}\n\n" if conversation_summary else ""
    ) + f"Demande de Victor:\n{message}\n\nRends le JSON du CEO."

    try:
        payload = await ask_ollama_json(
            CEO_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.1,
        )
    except OllamaClientError:
        # Repli prudent: on traite comme standard et on consulte les deux officiers.
        return CeoBrief(
            objective=message.strip()[:300],
            complexity="standard",
            needs_cto=True,
            needs_cfo=True,
            direct_answer="",
            needs_coo=True,
            rationale="CEO indisponible: delegation par defaut au CTO, CFO et COO.",
        )

    complexity = str(payload.get("complexity", "standard")).strip().lower()
    if complexity not in {"trivial", "standard", "complexe"}:
        complexity = "standard"

    needs_cto = _as_bool(payload.get("needs_cto"), default=complexity != "trivial")
    return CeoBrief(
        objective=str(payload.get("objective", message)).strip() or message.strip(),
        complexity=complexity,
        needs_cto=needs_cto,
        needs_cfo=_as_bool(payload.get("needs_cfo"), default=False),
        direct_answer=str(payload.get("direct_answer", "")).strip(),
        needs_coo=_as_bool(payload.get("needs_coo"), default=needs_cto),
        rationale=str(payload.get("rationale", "")).strip(),
    )

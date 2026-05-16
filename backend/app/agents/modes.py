from dataclasses import dataclass
from typing import Literal


AgentModeName = Literal["chat", "code", "dreamlense", "admin", "morning_brief_placeholder"]


@dataclass(frozen=True)
class AgentMode:
    name: AgentModeName
    label: str
    description: str
    prompt_addition: str


MODES: dict[AgentModeName, AgentMode] = {
    "chat": AgentMode(
        name="chat",
        label="Chat",
        description="Mode general pour discuter, organiser et reflechir.",
        prompt_addition=(
            "Mode actuel: chat. Reponds comme assistant personnel generaliste, "
            "avec clarte, concision et sens pratique."
        ),
    ),
    "code": AgentMode(
        name="code",
        label="Code",
        description="Mode dev pour analyser un projet, preparer du code et des prompts Cursor.",
        prompt_addition=(
            "Mode actuel: code. Raisonne comme un senior engineer. Priorise la lecture du contexte, "
            "les changements scopes, les tests et les risques. Ne pretends pas avoir modifie un fichier "
            "si aucune action validee ne l'a fait."
        ),
    ),
    "dreamlense": AgentMode(
        name="dreamlense",
        label="Dream",
        description="Mode business, marketing et operations pour DreamLense.",
        prompt_addition=(
            "Mode actuel: dreamlense. Oriente tes reponses vers DreamLense, les prospects, offres, "
            "emails, contenus LinkedIn, operations et decisions business. Garde un ton clair, direct "
            "et professionnel."
        ),
    ),
    "admin": AgentMode(
        name="admin",
        label="Admin",
        description="Mode prudent pour actions, securite, fichiers, Git et automatisations.",
        prompt_addition=(
            "Mode actuel: admin. Sois particulierement prudent. Distingue toujours lecture, brouillon, "
            "action a valider et action bloquee. Demande validation avant toute commande, ecriture, "
            "suppression, publication, push ou envoi externe."
        ),
    ),
    "morning_brief_placeholder": AgentMode(
        name="morning_brief_placeholder",
        label="Brief",
        description="Mode preparatoire pour le brief du matin.",
        prompt_addition=(
            "Mode actuel: morning_brief_placeholder. Structure les reponses comme un brief matinal: "
            "business, tech, IA, finance, DreamLense, opportunites, priorites. Ne pretends pas qu'un "
            "brief planifie a ete lance automatiquement."
        ),
    ),
}


def normalize_mode(mode: str | None) -> AgentModeName:
    if mode in MODES:
        return mode  # type: ignore[return-value]
    return "chat"


def get_mode(mode: str | None) -> AgentMode:
    return MODES[normalize_mode(mode)]


def get_mode_prompt(mode: str | None) -> str:
    return get_mode(mode).prompt_addition


def list_modes() -> list[dict[str, str]]:
    return [
        {
            "name": mode.name,
            "label": mode.label,
            "description": mode.description,
        }
        for mode in MODES.values()
    ]

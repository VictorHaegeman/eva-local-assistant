"""Règles permanentes d'Eva ("operating rules") réellement appliquées.

Différence avec la mémoire SQLite classique: ces règles sont des consignes durables
de comportement que Victor pose une fois, et qu'Eva doit appliquer à chaque réponse.
Elles sont injectées EN TÊTE du prompt système, marquées comme non négociables, pour
qu'Eva n'oblige plus Victor à tout réexpliquer à chaque message.

Stockage local simple et lisible: `data/eva_operating_rules.json`.
Aucun secret ne doit y être stocké (même garde-fou que la mémoire).
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class OperatingRulesError(Exception):
    """Raised when Eva cannot read or write the permanent operating rules."""


BACKEND_DIR = Path(__file__).resolve().parents[2]
RULES_PATH = BACKEND_DIR / "data" / "eva_operating_rules.json"

MAX_RULES = 60
MAX_RULE_LENGTH = 320

SENSITIVE_MARKERS = (
    "password",
    "mot de passe",
    "passwd",
    "token",
    "api key",
    "api_key",
    "apikey",
    "secret",
    "client secret",
    "cle secrete",
    "bearer ",
    "oauth",
)


@dataclass(frozen=True)
class OperatingRule:
    id: str
    text: str
    created_at: str


def rule_to_dict(rule: OperatingRule) -> dict[str, Any]:
    return {"id": rule.id, "text": rule.text, "created_at": rule.created_at}


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _looks_sensitive(text: str) -> bool:
    normalized = _normalize(text)
    return any(marker in normalized for marker in SENSITIVE_MARKERS)


def _read_raw() -> list[dict[str, Any]]:
    if not RULES_PATH.exists():
        return []
    try:
        payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OperatingRulesError("Fichier de règles permanentes illisible.") from exc
    if isinstance(payload, dict):
        payload = payload.get("rules", [])
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _write_raw(rules: list[dict[str, Any]]) -> None:
    try:
        RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        RULES_PATH.write_text(
            json.dumps({"rules": rules}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise OperatingRulesError("Impossible d'écrire les règles permanentes.") from exc


def list_operating_rules() -> list[OperatingRule]:
    rules: list[OperatingRule] = []
    for item in _read_raw():
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        rules.append(
            OperatingRule(
                id=str(item.get("id", "")),
                text=text,
                created_at=str(item.get("created_at", "")),
            )
        )
    return rules


def _next_id(existing: list[dict[str, Any]]) -> str:
    used = {str(item.get("id", "")) for item in existing}
    index = 1
    while f"rule-{index}" in used:
        index += 1
    return f"rule-{index}"


def add_operating_rule(text: str) -> OperatingRule:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) < 4:
        raise OperatingRulesError("Règle trop courte pour être utile.")
    if len(cleaned) > MAX_RULE_LENGTH:
        cleaned = cleaned[:MAX_RULE_LENGTH].rstrip()
    if _looks_sensitive(cleaned):
        raise OperatingRulesError("Refus: une règle permanente ne doit pas contenir de secret.")

    existing = _read_raw()
    normalized_new = _normalize(cleaned)
    for item in existing:
        if _normalize(str(item.get("text", ""))) == normalized_new:
            return OperatingRule(
                id=str(item.get("id", "")),
                text=str(item.get("text", "")),
                created_at=str(item.get("created_at", "")),
            )

    if len(existing) >= MAX_RULES:
        raise OperatingRulesError(
            f"Limite de {MAX_RULES} règles atteinte. Supprime une règle avant d'en ajouter."
        )

    rule = OperatingRule(
        id=_next_id(existing),
        text=cleaned,
        created_at=datetime.now(UTC).isoformat(),
    )
    existing.append(rule_to_dict(rule))
    _write_raw(existing)
    return rule


def remove_operating_rule(rule_id: str) -> bool:
    existing = _read_raw()
    remaining = [item for item in existing if str(item.get("id", "")) != rule_id]
    if len(remaining) == len(existing):
        return False
    _write_raw(remaining)
    return True


def build_operating_rules_prompt_context() -> str:
    """Bloc injecté EN TÊTE du prompt système, marqué comme non négociable."""
    rules = list_operating_rules()
    if not rules:
        return ""
    lines = [
        "REGLES PERMANENTES DE VICTOR (non negociables, appliquees a chaque reponse):",
    ]
    for index, rule in enumerate(rules, start=1):
        lines.append(f"{index}. {rule.text}")
    lines.append(
        "Applique ces regles par defaut sans les repeter a Victor. "
        "Si une demande contredit une regle permanente, signale-le brievement avant d'agir."
    )
    return "\n".join(lines)


def detect_operating_rule_command(message: str) -> str | None:
    """Détecte une consigne du type '/regle ...' ou 'retiens cette regle: ...'.

    Renvoie le texte de la règle à enregistrer, ou None si ce n'est pas une commande.
    """
    raw = (message or "").strip()
    if not raw:
        return None

    slash = re.match(r"^/(?:regle|règle|rule)\b[:\s]*(.+)$", raw, flags=re.IGNORECASE | re.DOTALL)
    if slash:
        return slash.group(1).strip() or None

    natural = re.match(
        r"^(?:retiens|memorise|mémorise|enregistre|garde)\s+(?:cette\s+|la\s+|une\s+)?"
        r"(?:regle|règle|consigne)\b[:\s]*(.+)$",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if natural:
        return natural.group(1).strip() or None

    return None

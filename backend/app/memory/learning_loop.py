import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.operator_journal import OperatorJournalError, OperatorTick, list_operator_ticks, operator_status
from app.config import settings
from app.memory.cluster_store import cluster_label, infer_memory_cluster
from app.memory.embedding_store import EmbeddingStoreError, rebuild_memory_embeddings
from app.memory.memory_store import (
    Memory,
    MemoryCandidate,
    MemoryStoreError,
    add_memory,
    detect_auto_memory_candidate,
    detect_operating_lesson_candidate,
    list_memories,
    memory_to_dict,
)
from app.memory.obsidian_store import ObsidianMemoryError, ensure_obsidian_vault, mirror_memory_to_obsidian


class MemoryLearningError(Exception):
    """Raised when Eva cannot consolidate local learning memories."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEARNING_REPORT_DIR = "80 - Learning"
LEARNING_REPORT_PREFIX = "Auto Learning"
MANAGED_MARKER = "<!-- eva:managed -->"


@dataclass(frozen=True)
class LearningCandidate:
    content: str
    category: str
    confidence: float
    reason: str


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _memory_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _normalize(text)).strip()


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _shorten(content: str, max_chars: int = 560) -> str:
    cleaned = " ".join(content.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


def _candidate(content: str, category: str, confidence: float, reason: str) -> LearningCandidate:
    return LearningCandidate(
        content=_shorten(content),
        category=category,
        confidence=min(max(float(confidence), 0.0), 1.0),
        reason=reason,
    )


def _from_memory_candidate(candidate: MemoryCandidate, reason: str) -> LearningCandidate:
    return _candidate(candidate.content, candidate.category, candidate.confidence, reason)


def _feedback_candidates(tick: OperatorTick) -> list[LearningCandidate]:
    message = _normalize(tick.message)
    candidates: list[LearningCandidate] = []

    if _has_any(message, ("frontend", "interface", "design", "affichage", "ui", "ux")) and _has_any(
        message,
        (
            "pas satisfait",
            "mal code",
            "trop complique",
            "lignes partout",
            "aucun sens",
            "beau",
            "coherence",
            "premium",
            "jarvis",
        ),
    ):
        candidates.append(
            _candidate(
                "Victor veut que le frontend Eva soit premium, lisible et utile: moins de lignes HUD gratuites, plus de coherence, d'animations de decision et de cartes exploitables.",
                "preference",
                0.9,
                "frontend_feedback",
            )
        )

    if _has_any(message, ("obsidian", "vault", "coffre")) and _has_any(
        message,
        ("memoire", "remplir", "riche", "clusters", "intelligente", "apprendre"),
    ):
        candidates.append(
            _candidate(
                "Eva doit enrichir Obsidian avec des notes reliees et actionnables: preferences de Victor, projets, regles, erreurs repetees, workflows qui marchent et idees a transformer.",
                "learning",
                0.9,
                "obsidian_learning_feedback",
            )
        )

    if _has_any(message, ("neural network", "machine learning", "embedding", "embeddings", "clusters", "cluster")):
        candidates.append(
            _candidate(
                "Pour devenir plus intelligente localement, Eva doit utiliser embeddings Ollama, clusters de memoire, recherche hybride FTS/vectorielle, consolidation Obsidian et feedback loop, sans entrainer un modele non controle.",
                "learning",
                0.92,
                "ml_memory_direction",
            )
        )

    if _has_any(message, ("perd le contexte", "perds le contexte", "telegram", "message d'apres", "message dapres")):
        candidates.append(
            _candidate(
                "Sur Telegram, Eva doit relire les derniers messages du fil et les souvenirs recents avant de router une demande courte ou une suite de conversation.",
                "operating_rule",
                0.9,
                "telegram_context_feedback",
            )
        )

    if _has_any(message, ("comprend rien", "comprends rien", "interprete plus", "fautes", "reflechisse", "reflechir")):
        candidates.append(
            _candidate(
                "Avant toute action, Eva doit reformuler mentalement l'objectif, corriger les fautes probables, choisir le domaine, recuperer le contexte utile, puis executer l'outil adapte au lieu de partir sur une recherche generique.",
                "operating_rule",
                0.93,
                "understanding_feedback",
            )
        )

    if _has_any(message, ("mail", "mails", "gmail")) and _has_any(
        message,
        ("dreamlense", "repondre", "reponse", "dernier", "non repondu", "pas encore repondu"),
    ):
        candidates.append(
            _candidate(
                "Pour les demandes Gmail de Victor, Eva doit lire les mails reels via Gmail API, filtrer par sujet/projet/date/thread, distinguer pubs et vrais mails humains, puis seulement resumer ou rediger.",
                "operating_rule",
                0.94,
                "gmail_task_feedback",
            )
        )

    if _has_any(message, ("pub", "pubs", "publicite", "publicites", "spam", "vrais mails", "mails importants")):
        candidates.append(
            _candidate(
                "Eva doit classer les emails entre publicite, notification automatique, alerte, newsletter et vrai mail humain avant de decider quoi lire, resumer ou traiter.",
                "operating_rule",
                0.88,
                "email_importance_feedback",
            )
        )

    return candidates


def _failure_candidates(tick: OperatorTick) -> list[LearningCandidate]:
    message = _normalize(tick.message)
    response = _normalize(tick.response)
    combined = f"{message} {response}"
    candidates: list[LearningCandidate] = []

    if "recherche web gratuite" in response and _has_any(message, ("mail", "mails", "gmail", "inbox")):
        candidates.append(
            _candidate(
                "Si Victor demande ses mails, Eva doit utiliser Gmail API ou demander une reconnexion Google; elle ne doit jamais remplacer les mails personnels par une recherche web generale.",
                "operating_rule",
                0.96,
                "gmail_web_misroute",
            )
        )

    if "recherche web gratuite" in response and _has_any(message, ("eteins", "eteint", "shutdown", "redemarre")):
        candidates.append(
            _candidate(
                "Pour une action systeme critique comme eteindre ou redemarrer le PC, Eva doit passer par la policy locale et expliquer le blocage ou la validation requise, pas lancer une recherche web.",
                "operating_rule",
                0.9,
                "system_action_misroute",
            )
        )

    if "il me manque le projet cible" in response or "projet cible" in response:
        if _has_any(message, ("cursor agent", "installe", "installer", "installation", "tous les projets")):
            candidates.append(
                _candidate(
                    "Installer ou activer Cursor Agent est une demande d'environnement global; Eva ne doit pas demander un projet cible pour cette intention.",
                    "operating_rule",
                    0.95,
                    "cursor_agent_setup_misroute",
                )
            )
        else:
            candidates.append(
                _candidate(
                    "Quand le projet cible est flou, Eva doit faire un fuzzy matching sur les projets connus, utiliser le contexte recent et proposer le meilleur match avant de demander a Victor.",
                    "operating_rule",
                    0.92,
                    "project_fuzzy_match_needed",
                )
            )

    if _has_any(response, ("je ne peux pas ouvrir", "je ne peux pas interagir", "je suis une assistante virtuelle")):
        candidates.append(
            _candidate(
                "Eva ne doit pas repondre en posture assistant virtuel quand une action locale existe; elle doit essayer browser_assistant, desktop_automation, screen_navigation ou un plan B autorise.",
                "operating_rule",
                0.94,
                "passive_refusal",
            )
        )

    if "invalid_grant" in combined or "token has been expired or revoked" in combined:
        candidates.append(
            _candidate(
                "Si Gmail renvoie invalid_grant, Eva doit expliquer que le token Google est expire/revoque et lancer une reconnexion OAuth au lieu de continuer les memes essais.",
                "operating_rule",
                0.95,
                "gmail_oauth_recovery",
            )
        )

    if "aucun resultat web exploitable" in response:
        candidates.append(
            _candidate(
                "Si une recherche web echoue, Eva doit reformuler la requete, changer de source ou ouvrir une page evidente dans Brave avant de conclure.",
                "operating_rule",
                0.86,
                "web_search_recovery",
            )
        )

    if "aucune destination navigateur fiable" in response:
        candidates.append(
            _candidate(
                "Si une demande d'ouverture web n'a pas d'URL explicite, Eva doit extraire l'intention, choisir le site probable ou ouvrir une recherche Brave ciblee.",
                "operating_rule",
                0.87,
                "browser_destination_recovery",
            )
        )

    if tick.reflex_note and "aucune relance automatique necessaire" not in _normalize(tick.reflex_note):
        candidates.append(_candidate(tick.reflex_note, "operating_rule", 0.82, "operator_reflex"))

    return candidates


def learning_candidates_from_tick(tick: OperatorTick) -> list[LearningCandidate]:
    candidates: list[LearningCandidate] = []

    try:
        auto_candidate = detect_auto_memory_candidate(tick.message)
    except MemoryStoreError:
        auto_candidate = None
    if auto_candidate:
        candidates.append(_from_memory_candidate(auto_candidate, "auto_memory"))

    try:
        operating_candidate = detect_operating_lesson_candidate(tick.message)
    except MemoryStoreError:
        operating_candidate = None
    if operating_candidate:
        candidates.append(_from_memory_candidate(operating_candidate, "explicit_operating_lesson"))

    candidates.extend(_feedback_candidates(tick))
    if tick.status in {"needs_followup", "blocked", "failed"} or tick.reflex_note:
        candidates.extend(_failure_candidates(tick))

    deduped: list[LearningCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _memory_key(candidate.content)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _recent_memory_keys() -> set[str]:
    try:
        return {_memory_key(memory.content) for memory in list_memories(limit=200)}
    except MemoryStoreError:
        return set()


def _store_candidate(
    candidate: LearningCandidate,
    known_keys: set[str],
    *,
    mirror: bool,
) -> tuple[Memory | None, str]:
    key = _memory_key(candidate.content)
    if not key:
        return None, "empty"
    if key in known_keys:
        return None, "duplicate"

    try:
        memory = add_memory(
            candidate.content,
            category=candidate.category,
            source="learning_loop",
            confidence=candidate.confidence,
        )
    except MemoryStoreError:
        return None, "rejected"

    known_keys.add(key)
    if mirror:
        try:
            mirror_memory_to_obsidian(memory)
        except ObsidianMemoryError:
            pass
    return memory, "stored"


def learn_from_tick(tick: OperatorTick, *, mirror: bool = True) -> dict[str, object]:
    if not settings.eva_memory_learning_enabled:
        return {"enabled": False, "stored": 0, "candidates": 0}

    known_keys = _recent_memory_keys()
    stored: list[dict[str, object]] = []
    skipped = Counter()
    candidates = learning_candidates_from_tick(tick)

    for candidate in candidates:
        memory, status = _store_candidate(candidate, known_keys, mirror=mirror)
        if memory:
            stored.append(
                {
                    **memory_to_dict(memory),
                    "cluster_key": infer_memory_cluster(memory),
                    "reason": candidate.reason,
                }
            )
        else:
            skipped[status] += 1

    return {
        "enabled": True,
        "tick_id": tick.id,
        "candidates": len(candidates),
        "stored": len(stored),
        "skipped": dict(skipped),
        "memories": stored,
    }


def _write_learning_report(
    stored: list[dict[str, object]],
    *,
    ticks_analyzed: int,
    skipped: Counter,
    embeddings: dict[str, object],
) -> dict[str, object]:
    vault = ensure_obsidian_vault()
    report_dir = vault / LEARNING_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    date_key = datetime.now().date().isoformat()
    report_path = report_dir / f"{LEARNING_REPORT_PREFIX} {date_key}.md"

    cluster_counts = Counter(str(memory.get("cluster_key", "general")) for memory in stored)
    lines = [
        MANAGED_MARKER,
        f"# Eva Learning Report - {date_key}",
        "",
        "## Resume",
        f"- Ticks analyses: {ticks_analyzed}",
        f"- Nouveaux souvenirs: {len(stored)}",
        f"- Doublons ignores: {skipped.get('duplicate', 0)}",
        f"- Rejets securite/format: {skipped.get('rejected', 0)}",
        f"- Embeddings: {'reconstruits' if embeddings.get('rebuilt') else 'non reconstruits'}",
        "",
        "## Clusters touches",
    ]
    if cluster_counts:
        for cluster_key, count in cluster_counts.most_common():
            lines.append(f"- [[{cluster_label(cluster_key)}]]: {count}")
    else:
        lines.append("- Aucun nouveau cluster.")

    lines.extend(["", "## Souvenirs ajoutes"])
    if stored:
        for memory in stored[:80]:
            category = str(memory.get("category", "general"))
            cluster_key = str(memory.get("cluster_key", "general"))
            content = str(memory.get("content", ""))
            reason = str(memory.get("reason", "learning"))
            lines.append(f"- #{category} [[{cluster_label(cluster_key)}]] ({reason}) {content}")
    else:
        lines.append("- Rien de nouveau a ajouter. Les apprentissages etaient deja presents.")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(report_path),
        "relative_path": report_path.relative_to(vault).as_posix(),
    }


def consolidate_learning(limit: int = 120, rebuild_embeddings: bool = False) -> dict[str, object]:
    if not settings.eva_memory_learning_enabled:
        return {
            "enabled": False,
            "stored": 0,
            "message": "Boucle d'apprentissage locale desactivee.",
        }

    safe_limit = min(max(int(limit), 1), 500)
    try:
        ticks = list_operator_ticks(limit=safe_limit)
    except OperatorJournalError as exc:
        raise MemoryLearningError(str(exc)) from exc

    known_keys = _recent_memory_keys()
    stored: list[dict[str, object]] = []
    skipped = Counter()
    candidate_count = 0

    for tick in reversed(ticks):
        candidates = learning_candidates_from_tick(tick)
        candidate_count += len(candidates)
        for candidate in candidates:
            memory, status = _store_candidate(candidate, known_keys, mirror=True)
            if memory:
                stored.append(
                    {
                        **memory_to_dict(memory),
                        "cluster_key": infer_memory_cluster(memory),
                        "reason": candidate.reason,
                    }
                )
            else:
                skipped[status] += 1

    embeddings: dict[str, object] = {"rebuilt": False}
    if rebuild_embeddings and stored and settings.eva_embeddings_enabled:
        try:
            embeddings = {
                "rebuilt": True,
                **rebuild_memory_embeddings(limit=min(1000, max(250, len(stored) + 200))),
            }
        except EmbeddingStoreError as exc:
            embeddings = {"rebuilt": False, "error": str(exc)}

    try:
        report = _write_learning_report(
            stored,
            ticks_analyzed=len(ticks),
            skipped=skipped,
            embeddings=embeddings,
        )
    except (OSError, ObsidianMemoryError) as exc:
        raise MemoryLearningError("Impossible d'ecrire le rapport d'apprentissage Obsidian.") from exc

    cluster_counts = Counter(str(memory.get("cluster_key", "general")) for memory in stored)
    return {
        "enabled": True,
        "ticks_analyzed": len(ticks),
        "candidates": candidate_count,
        "stored": len(stored),
        "skipped": dict(skipped),
        "clusters": [
            {
                "key": key,
                "label": cluster_label(key),
                "count": count,
            }
            for key, count in cluster_counts.most_common()
        ],
        "report": report,
        "embeddings": embeddings,
        "memories": stored[:50],
    }


def learning_status() -> dict[str, object]:
    enabled = settings.eva_memory_learning_enabled
    try:
        status = operator_status()
    except OperatorJournalError:
        status = {"ticks": 0, "needs_followup": 0}

    try:
        memories = list_memories(limit=200)
    except MemoryStoreError:
        memories = []

    learning_memories = [
        memory
        for memory in memories
        if memory.source == "learning_loop" or memory.category in {"learning", "operating_rule"}
    ]
    cluster_counts = Counter(infer_memory_cluster(memory) for memory in learning_memories)

    report_count = 0
    last_report = ""
    try:
        vault = ensure_obsidian_vault()
        reports = sorted((vault / LEARNING_REPORT_DIR).glob(f"{LEARNING_REPORT_PREFIX}*.md"))
        report_count = len(reports)
        last_report = str(reports[-1]) if reports else ""
    except ObsidianMemoryError:
        pass

    return {
        "enabled": enabled,
        "recent_tick_limit": settings.eva_memory_learning_recent_ticks,
        "operator_ticks": status.get("ticks", 0),
        "needs_followup": status.get("needs_followup", 0),
        "learning_memories": len(learning_memories),
        "report_count": report_count,
        "last_report": last_report,
        "clusters": [
            {
                "key": key,
                "label": cluster_label(key),
                "count": count,
            }
            for key, count in cluster_counts.most_common(8)
        ],
    }

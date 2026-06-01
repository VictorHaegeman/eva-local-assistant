import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.memory.embedding_store import EmbeddingStoreError, rebuild_memory_embeddings
from app.memory.memory_store import MemoryStoreError, add_memory, delete_memory, list_memories, memory_to_dict
from app.memory.obsidian_store import ObsidianMemoryError, ensure_obsidian_vault, mirror_memory_to_obsidian


class KnowledgeIngestionError(Exception):
    """Raised when Eva cannot import local knowledge documents."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANAGED_MARKER = "<!-- eva:managed -->"
KNOWLEDGE_ROOT = "75 - Knowledge"
ML_ROOT = "Machine Learning"

STOPWORDS = {
    "avec",
    "about",
    "after",
    "also",
    "and",
    "are",
    "aux",
    "can",
    "ces",
    "dans",
    "data",
    "des",
    "for",
    "from",
    "how",
    "les",
    "machine",
    "model",
    "models",
    "not",
    "our",
    "par",
    "pour",
    "que",
    "qui",
    "sur",
    "the",
    "this",
    "une",
    "using",
    "with",
}


@dataclass(frozen=True)
class KnowledgeMemoryItem:
    category: str
    content: str
    confidence: float = 0.86


@dataclass(frozen=True)
class KnowledgeTopic:
    key: str
    label: str
    concepts: tuple[str, ...]
    eva_lessons: tuple[str, ...]


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(text).lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _safe_slug(value: str) -> str:
    normalized = _normalize(value)
    cleaned = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return cleaned[:90] or "knowledge"


def _shorten(text: str, limit: int = 560) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _resolve_source_dir(source_dir: str) -> Path:
    raw = Path(source_dir or "docs").expanduser()
    if not raw.is_absolute():
        raw = PROJECT_ROOT / raw
    resolved = raw.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise KnowledgeIngestionError("Le dossier de connaissances doit rester dans le projet Eva.") from exc
    if not resolved.exists() or not resolved.is_dir():
        raise KnowledgeIngestionError(f"Dossier introuvable: {resolved}")
    return resolved


def _load_pdf_reader() -> Any:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise KnowledgeIngestionError(
            "Lecture PDF indisponible. Lance: pip install -r backend/requirements.txt"
        ) from exc
    return PdfReader


def _pdf_files(source_dir: Path, pattern: str, limit: int) -> list[Path]:
    safe_limit = min(max(int(limit), 1), 100)
    return sorted(source_dir.glob(pattern or "*.pdf"))[:safe_limit]


def _title_from_path(path: Path) -> str:
    title = path.stem
    title = re.sub(r"^CX[\d.-]+-IML\s*-\s*\d+\s*-\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip()
    return title or path.stem


def _extract_pdf_text(path: Path, max_pages: int) -> tuple[str, int]:
    PdfReader = _load_pdf_reader()
    try:
        reader = PdfReader(str(path))
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                pass
        pages = list(reader.pages)
    except Exception as exc:
        raise KnowledgeIngestionError(f"Impossible de lire le PDF {path.name}: {exc}") from exc

    page_limit = min(max(int(max_pages), 1), len(pages), 80)
    chunks: list[str] = []
    for page in pages[:page_limit]:
        try:
            chunks.append(page.extract_text() or "")
        except Exception:
            continue

    text = re.sub(r"\s+", " ", "\n".join(chunks)).strip()
    return text, page_limit


def _top_terms(text: str, limit: int = 10) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", _normalize(text))
    counter = Counter(token for token in tokens if token not in STOPWORDS)
    return [term for term, _ in counter.most_common(limit)]


def _topic_for_title(title: str, text: str = "") -> KnowledgeTopic:
    title_normalized = _normalize(title)
    normalized = _normalize(f"{title} {text[:1000]}")

    def title_has(*markers: str) -> bool:
        return any(marker in title_normalized for marker in markers)

    if title_has("cross-validation", "cross validation"):
        return KnowledgeTopic(
            key="cross_validation",
            label="Cross-Validation",
            concepts=(
                "La cross-validation teste un modele sur plusieurs decoupages de donnees.",
                "Elle donne une estimation plus robuste que split unique.",
                "Elle aide a comparer des variantes sans se fier a un seul essai.",
            ),
            eva_lessons=(
                "Eva doit tester plusieurs routes quand une action echoue, puis garder celle qui donne les meilleures preuves.",
                "Un seul echec ne suffit pas: Eva doit classer les alternatives et apprendre des essais.",
            ),
        )

    if title_has("metrics", "evaluation"):
        return KnowledgeTopic(
            key="metrics_evaluation",
            label="Metrics Evaluation",
            concepts=(
                "Les metriques permettent de comparer les modeles et les decisions.",
                "Accuracy, precision, recall et F1 ne mesurent pas la meme chose.",
                "Le choix de la metrique depend du risque d'erreur.",
            ),
            eva_lessons=(
                "Eva doit evaluer ses actions avec des rewards, preuves locales et penalites de mauvaise route.",
                "Pour Gmail ou actions PC, la precision compte plus qu'une reponse rapide mais fausse.",
            ),
        )

    if title_has("training process", "training"):
        return KnowledgeTopic(
            key="training_process",
            label="Training Process",
            concepts=(
                "Un processus d'entrainement organise donnees, modele, pertes, evaluation et iteration.",
                "Le risque d'overfitting impose validation et regularisation.",
                "La qualite des donnees influence directement la qualite du modele.",
            ),
            eva_lessons=(
                "Eva doit apprendre par boucle: tentative, preuve, critique, reward, consolidation.",
                "Eva doit filtrer les souvenirs inutiles pour eviter de surapprendre du bruit.",
            ),
        )

    if title_has("python for data science", "python"):
        return KnowledgeTopic(
            key="python_data_science",
            label="Python for Data Science",
            concepts=(
                "Python sert a charger, nettoyer, transformer et analyser les donnees.",
                "Les notebooks et scripts doivent rester reproductibles.",
                "La preparation des donnees est souvent plus importante que le modele.",
            ),
            eva_lessons=(
                "Eva doit privilegier des pipelines reproductibles pour ses imports, audits et briefs.",
                "Eva doit nettoyer le texte avant embeddings, recherche et clustering.",
            ),
        )

    if title_has("nearest neighbors", "knn"):
        return KnowledgeTopic(
            key="knn",
            label="K-Nearest Neighbors",
            concepts=(
                "KNN classe ou predit en regardant les exemples les plus proches dans l'espace des features.",
                "KNN est sensible au scaling des variables et au choix de k.",
                "KNN sert bien de baseline simple avant des modeles plus complexes.",
            ),
            eva_lessons=(
                "Pour une demande floue, Eva peut raisonner comme KNN: chercher les cas passes les plus proches avant de choisir une action.",
                "Eva doit normaliser les signaux de contexte pour eviter qu'un mot dominant ecrase le reste.",
            ),
        )

    if title_has("regression"):
        return KnowledgeTopic(
            key="regression",
            label="Regression",
            concepts=(
                "La regression predit une valeur continue a partir de variables explicatives.",
                "Les residus aident a voir ce que le modele explique mal.",
                "Les metriques comme MAE, MSE ou RMSE mesurent l'erreur de prediction.",
            ),
            eva_lessons=(
                "Eva doit mesurer l'ecart entre objectif demande et resultat obtenu pour progresser.",
                "Les echecs repetes doivent devenir des signaux de correction, pas des excuses.",
            ),
        )

    if title_has("k-means", "kmeans"):
        return KnowledgeTopic(
            key="kmeans",
            label="K-Means Clustering",
            concepts=(
                "K-Means regroupe des donnees proches autour de centroides.",
                "Le nombre de clusters influence fortement l'interpretation.",
                "Les clusters sont utiles pour organiser une memoire, mais ne remplacent pas la verification.",
            ),
            eva_lessons=(
                "Eva doit clusteriser souvenirs, erreurs, projets et preferences pour retrouver le bon contexte plus vite.",
                "Eva doit garder une recherche hybride: clusters comme boussole, FTS et embeddings comme preuve.",
            ),
        )

    if title_has("hierarchical", "hierarch"):
        return KnowledgeTopic(
            key="hierarchical_clustering",
            label="Hierarchical Clustering",
            concepts=(
                "Le clustering hierarchique construit des groupes imbriques de similarite.",
                "Un dendrogramme aide a voir les niveaux de regroupement.",
                "Cette approche est utile quand le nombre de clusters n'est pas evident.",
            ),
            eva_lessons=(
                "Eva peut relier ses notes Obsidian en niveaux: Victor, projets, workflows, erreurs, actions.",
                "Eva doit remonter du detail vers le bon niveau de contexte avant d'agir.",
            ),
        )

    if title_has("machine learning"):
        return KnowledgeTopic(
            key="machine_learning_intro",
            label="Machine Learning Introduction",
            concepts=(
                "Le machine learning apprend des patterns a partir de donnees et d'objectifs.",
                "Les donnees, features, labels et evaluation structurent tout pipeline ML.",
                "Un modele utile doit generaliser au dela des exemples vus.",
            ),
            eva_lessons=(
                "Eva doit transformer les interactions en donnees locales structurees: demande, route, preuve, resultat, feedback.",
                "Eva ne doit pas confondre confiance apparente et preuve verifiee.",
            ),
        )

    if title_has("unsupervised"):
        return KnowledgeTopic(
            key="unsupervised_learning",
            label="Unsupervised Learning",
            concepts=(
                "L'apprentissage non supervise cherche des structures sans labels explicites.",
                "Il sert a explorer, segmenter et detecter des patterns.",
                "Les resultats doivent etre interpretes avec prudence car les clusters ne sont pas des verites absolues.",
            ),
            eva_lessons=(
                "Eva peut decouvrir des patterns dans les demandes de Victor, mais doit toujours verifier avant d'agir.",
                "Les notes Obsidian peuvent devenir une carte de patterns plutot qu'un simple stockage.",
            ),
        )

    if title_has("supervised"):
        return KnowledgeTopic(
            key="supervised_learning",
            label="Supervised Learning",
            concepts=(
                "L'apprentissage supervise apprend a partir d'exemples etiquetes.",
                "La separation train/test sert a mesurer la generalisation.",
                "Un bon modele optimise un objectif mesurable sans surapprendre les exemples.",
            ),
            eva_lessons=(
                "Le feedback de Victor peut servir de label local: bonne route, mauvaise route, action reussie.",
                "Eva doit apprendre de ses erreurs mesurees sans modifier aveuglement son comportement.",
            ),
        )

    if "nearest neighbors" in normalized or "knn" in normalized:
        return KnowledgeTopic(
            key="knn",
            label="K-Nearest Neighbors",
            concepts=(
                "KNN classe ou predit en regardant les exemples les plus proches dans l'espace des features.",
                "KNN est sensible au scaling des variables et au choix de k.",
                "KNN sert bien de baseline simple avant des modeles plus complexes.",
            ),
            eva_lessons=(
                "Pour une demande floue, Eva peut raisonner comme KNN: chercher les cas passes les plus proches avant de choisir une action.",
                "Eva doit normaliser les signaux de contexte pour eviter qu'un mot dominant ecrase le reste.",
            ),
        )

    if "regression" in normalized:
        return KnowledgeTopic(
            key="regression",
            label="Regression",
            concepts=(
                "La regression predit une valeur continue a partir de variables explicatives.",
                "Les residus aident a voir ce que le modele explique mal.",
                "Les metriques comme MAE, MSE ou RMSE mesurent l'erreur de prediction.",
            ),
            eva_lessons=(
                "Eva doit mesurer l'ecart entre objectif demande et resultat obtenu pour progresser.",
                "Les echecs repetes doivent devenir des signaux de correction, pas des excuses.",
            ),
        )

    if "k-means" in normalized or "kmeans" in normalized:
        return KnowledgeTopic(
            key="kmeans",
            label="K-Means Clustering",
            concepts=(
                "K-Means regroupe des donnees proches autour de centroides.",
                "Le nombre de clusters influence fortement l'interpretation.",
                "Les clusters sont utiles pour organiser une memoire, mais ne remplacent pas la verification.",
            ),
            eva_lessons=(
                "Eva doit clusteriser souvenirs, erreurs, projets et preferences pour retrouver le bon contexte plus vite.",
                "Eva doit garder une recherche hybride: clusters comme boussole, FTS et embeddings comme preuve.",
            ),
        )

    if "hierarchical" in normalized or "hierarch" in normalized:
        return KnowledgeTopic(
            key="hierarchical_clustering",
            label="Hierarchical Clustering",
            concepts=(
                "Le clustering hierarchique construit des groupes imbriques de similarite.",
                "Un dendrogramme aide a voir les niveaux de regroupement.",
                "Cette approche est utile quand le nombre de clusters n'est pas evident.",
            ),
            eva_lessons=(
                "Eva peut relier ses notes Obsidian en niveaux: Victor, projets, workflows, erreurs, actions.",
                "Eva doit remonter du detail vers le bon niveau de contexte avant d'agir.",
            ),
        )

    if "unsupervised" in normalized:
        return KnowledgeTopic(
            key="unsupervised_learning",
            label="Unsupervised Learning",
            concepts=(
                "L'apprentissage non supervise cherche des structures sans labels explicites.",
                "Il sert a explorer, segmenter et detecter des patterns.",
                "Les resultats doivent etre interpretes avec prudence car les clusters ne sont pas des verites absolues.",
            ),
            eva_lessons=(
                "Eva peut decouvrir des patterns dans les demandes de Victor, mais doit toujours verifier avant d'agir.",
                "Les notes Obsidian peuvent devenir une carte de patterns plutot qu'un simple stockage.",
            ),
        )

    if "supervised" in normalized:
        return KnowledgeTopic(
            key="supervised_learning",
            label="Supervised Learning",
            concepts=(
                "L'apprentissage supervise apprend a partir d'exemples etiquetes.",
                "La separation train/test sert a mesurer la generalisation.",
                "Un bon modele optimise un objectif mesurable sans surapprendre les exemples.",
            ),
            eva_lessons=(
                "Le feedback de Victor peut servir de label local: bonne route, mauvaise route, action reussie.",
                "Eva doit apprendre de ses erreurs mesurees sans modifier aveuglement son comportement.",
            ),
        )

    if "metrics" in normalized or "evaluation" in normalized:
        return KnowledgeTopic(
            key="metrics_evaluation",
            label="Metrics Evaluation",
            concepts=(
                "Les metriques permettent de comparer les modeles et les decisions.",
                "Accuracy, precision, recall et F1 ne mesurent pas la meme chose.",
                "Le choix de la metrique depend du risque d'erreur.",
            ),
            eva_lessons=(
                "Eva doit evaluer ses actions avec des rewards, preuves locales et penalites de mauvaise route.",
                "Pour Gmail ou actions PC, la precision compte plus qu'une reponse rapide mais fausse.",
            ),
        )

    if "training process" in normalized or "training" in normalized:
        return KnowledgeTopic(
            key="training_process",
            label="Training Process",
            concepts=(
                "Un processus d'entrainement organise donnees, modele, pertes, evaluation et iteration.",
                "Le risque d'overfitting impose validation et regularisation.",
                "La qualite des donnees influence directement la qualite du modele.",
            ),
            eva_lessons=(
                "Eva doit apprendre par boucle: tentative, preuve, critique, reward, consolidation.",
                "Eva doit filtrer les souvenirs inutiles pour eviter de surapprendre du bruit.",
            ),
        )

    if "cross-validation" in normalized or "cross validation" in normalized:
        return KnowledgeTopic(
            key="cross_validation",
            label="Cross-Validation",
            concepts=(
                "La cross-validation teste un modele sur plusieurs decoupages de donnees.",
                "Elle donne une estimation plus robuste que split unique.",
                "Elle aide a comparer des variantes sans se fier a un seul essai.",
            ),
            eva_lessons=(
                "Eva doit tester plusieurs routes quand une action echoue, puis garder celle qui donne les meilleures preuves.",
                "Un seul echec ne suffit pas: Eva doit classer les alternatives et apprendre des essais.",
            ),
        )

    if "python for data science" in normalized or "python" in normalized:
        return KnowledgeTopic(
            key="python_data_science",
            label="Python for Data Science",
            concepts=(
                "Python sert a charger, nettoyer, transformer et analyser les donnees.",
                "Les notebooks et scripts doivent rester reproductibles.",
                "La preparation des donnees est souvent plus importante que le modele.",
            ),
            eva_lessons=(
                "Eva doit privilegier des pipelines reproductibles pour ses imports, audits et briefs.",
                "Eva doit nettoyer le texte avant embeddings, recherche et clustering.",
            ),
        )

    if "introduction" in normalized and "machine learning" in normalized:
        return KnowledgeTopic(
            key="ml_intro",
            label="Introduction Machine Learning",
            concepts=(
                "Le machine learning apprend des patterns dans les donnees pour predire, classer ou recommander.",
                "Les grands types sont supervise, non supervise et reinforcement learning.",
                "Un systeme intelligent combine donnees, objectifs, evaluation et iteration.",
            ),
            eva_lessons=(
                "Eva doit rester un systeme local qui combine LLM, memoire, outils, evaluation et apprentissage.",
                "Ollama n'est qu'une brique: le vrai gain vient du contexte, des outils et de la boucle de feedback.",
            ),
        )

    terms = _top_terms(text, limit=6)
    return KnowledgeTopic(
        key="machine_learning",
        label="Machine Learning",
        concepts=(
            "Ce document enrichit la base locale de concepts machine learning d'Eva.",
            f"Termes dominants detectes: {', '.join(terms) if terms else 'non detectes'}.",
        ),
        eva_lessons=(
            "Eva doit utiliser ces connaissances comme contexte RAG local, pas comme entrainement non controle.",
            "Eva doit transformer les concepts utiles en regles actionnables et verifier leurs effets.",
        ),
    )


def _memory_items(title: str, topic: KnowledgeTopic, terms: list[str]) -> list[KnowledgeMemoryItem]:
    items = [
        KnowledgeMemoryItem(
            category="learning",
            content=f"Knowledge ML - {topic.label}: {concept}",
            confidence=0.86,
        )
        for concept in topic.concepts
    ]
    items.extend(
        KnowledgeMemoryItem(
            category="operating_rule",
            content=lesson,
            confidence=0.9,
        )
        for lesson in topic.eva_lessons
    )
    if terms:
        items.append(
            KnowledgeMemoryItem(
                category="learning",
                content=(
                    f"Document ML '{title}' indexe dans Eva; mots cles locaux utiles: "
                    f"{', '.join(terms[:8])}."
                ),
                confidence=0.78,
            )
        )
    return [
        KnowledgeMemoryItem(item.category, _shorten(item.content), item.confidence)
        for item in items
    ]


def _extract_excerpts(text: str, limit: int = 4) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean_sentences = [
        _shorten(sentence, 220)
        for sentence in sentences
        if 60 <= len(sentence.strip()) <= 260
    ]
    return clean_sentences[:limit]


def _knowledge_note_path(vault: Path, title: str) -> Path:
    return vault / KNOWLEDGE_ROOT / ML_ROOT / f"{_safe_slug(title)}.md"


def _clear_managed_knowledge_notes(vault: Path) -> int:
    knowledge_dir = vault / KNOWLEDGE_ROOT / ML_ROOT
    if not knowledge_dir.exists():
        return 0

    deleted = 0
    for note_path in knowledge_dir.glob("*.md"):
        try:
            content = note_path.read_text(encoding="utf-8")
        except OSError:
            continue
        if MANAGED_MARKER not in content[:200]:
            continue
        try:
            note_path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted


def _delete_existing_knowledge_memories() -> int:
    deleted = 0
    for _ in range(5):
        batch = [memory for memory in list_memories(limit=200) if memory.source == "knowledge_pdf"]
        if not batch:
            break
        for memory in batch:
            if delete_memory(memory.id):
                deleted += 1
    return deleted


def _write_knowledge_note(
    vault: Path,
    *,
    title: str,
    source_path: Path,
    topic: KnowledgeTopic,
    pages_read: int,
    terms: list[str],
    memories: list[KnowledgeMemoryItem],
    excerpts: list[str],
) -> dict[str, object]:
    note_path = _knowledge_note_path(vault, title)
    note_path.parent.mkdir(parents=True, exist_ok=True)
    relative_source = source_path.relative_to(PROJECT_ROOT).as_posix()
    lines = [
        MANAGED_MARKER,
        f"# {title}",
        "",
        f"- Source: `{relative_source}`",
        f"- Topic: [[{topic.label}]]",
        f"- Pages lues: {pages_read}",
        "- Type: knowledge import local",
        "",
        "## Concepts",
    ]
    lines.extend(f"- {concept}" for concept in topic.concepts)
    lines.extend(["", "## Implications pour Eva"])
    lines.extend(f"- {lesson}" for lesson in topic.eva_lessons)
    lines.extend(["", "## Mots cles"])
    lines.append(", ".join(terms) if terms else "Aucun mot cle stable detecte.")
    lines.extend(["", "## Memories importees"])
    lines.extend(f"- #memory/{item.category} {item.content}" for item in memories)
    lines.extend(["", "## Extraits locaux"])
    if excerpts:
        lines.extend(f"- {excerpt}" for excerpt in excerpts)
    else:
        lines.append("- Aucun extrait textuel exploitable.")
    lines.extend(["", "## Liens", "- [[Machine Learning Knowledge]]", "- [[INDEX]]"])
    note_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(note_path),
        "relative_path": note_path.relative_to(vault).as_posix(),
    }


def _write_knowledge_index(vault: Path, documents: list[dict[str, object]]) -> dict[str, object]:
    index_path = vault / KNOWLEDGE_ROOT / ML_ROOT / "Machine Learning Knowledge.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        MANAGED_MARKER,
        "# Machine Learning Knowledge",
        "",
        "Base locale issue des PDFs ajoutes dans `docs/`.",
        "Eva utilise cette base comme contexte RAG local: Obsidian + SQLite + embeddings Ollama.",
        "",
        "## Documents indexes",
    ]
    if documents:
        for document in documents:
            note = str(document.get("note_relative_path", ""))
            title = str(document.get("title", "Document"))
            topic = str(document.get("topic", "Machine Learning"))
            if note:
                note_name = Path(note).stem
                lines.append(f"- [[{note_name}|{title}]] - {topic}")
            else:
                lines.append(f"- {title} - {topic}")
    else:
        lines.append("- Aucun document importe.")
    lines.extend(
        [
            "",
            "## Comment Eva doit s'en servir",
            "- Retrouver les concepts proches via FTS + embeddings.",
            "- Transformer les concepts en choix d'action, pas en blabla theorique.",
            "- Penaliser les mauvaises routes et consolider les corrections de Victor.",
            "- Garder les PDFs et notes localement; aucun cloud obligatoire.",
        ]
    )
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(index_path),
        "relative_path": index_path.relative_to(vault).as_posix(),
    }


def knowledge_ingestion_status(
    source_dir: str = "docs",
    pattern: str = "*.pdf",
) -> dict[str, object]:
    source = _resolve_source_dir(source_dir)
    try:
        _load_pdf_reader()
        pdf_reader_available = True
    except KnowledgeIngestionError:
        pdf_reader_available = False

    pdfs = _pdf_files(source, pattern, 100)
    notes = 0
    vault_path = ""
    try:
        vault = ensure_obsidian_vault()
        vault_path = str(vault)
        knowledge_dir = vault / KNOWLEDGE_ROOT / ML_ROOT
        notes = len(list(knowledge_dir.glob("*.md"))) if knowledge_dir.exists() else 0
    except ObsidianMemoryError:
        pass

    memories = []
    try:
        memories = [
            memory_to_dict(memory)
            for memory in list_memories(limit=200)
            if memory.source == "knowledge_pdf"
        ]
    except MemoryStoreError:
        memories = []

    return {
        "source_dir": str(source),
        "pattern": pattern,
        "pdf_reader_available": pdf_reader_available,
        "pdf_count": len(pdfs),
        "pdfs": [
            {
                "name": path.name,
                "size": path.stat().st_size,
            }
            for path in pdfs[:40]
        ],
        "obsidian_vault": vault_path,
        "knowledge_notes": notes,
        "knowledge_memories": len(memories),
        "recent_memories": memories[:20],
    }


def import_machine_learning_knowledge(
    *,
    source_dir: str = "docs",
    pattern: str = "*.pdf",
    limit: int = 20,
    max_pages: int = 14,
    import_to_sqlite: bool = True,
    write_obsidian: bool = True,
    rebuild_embeddings: bool = False,
    replace_existing: bool = True,
) -> dict[str, object]:
    source = _resolve_source_dir(source_dir)
    pdfs = _pdf_files(source, pattern, limit)
    if not pdfs:
        return {
            "imported_documents": 0,
            "imported_memories": 0,
            "message": "Aucun PDF trouve.",
            "source_dir": str(source),
        }

    vault = ensure_obsidian_vault() if write_obsidian else None
    deleted_notes = _clear_managed_knowledge_notes(vault) if vault and replace_existing else 0
    deleted_memories = _delete_existing_knowledge_memories() if import_to_sqlite and replace_existing else 0
    documents: list[dict[str, object]] = []
    imported_memories: list[dict[str, object]] = []
    imported_memory_ids: set[int] = set()
    errors: list[str] = []

    for pdf_path in pdfs:
        try:
            title = _title_from_path(pdf_path)
            text, pages_read = _extract_pdf_text(pdf_path, max_pages=max_pages)
            topic = _topic_for_title(title, text)
            terms = _top_terms(text)
            memories = _memory_items(title, topic, terms)
            excerpts = _extract_excerpts(text)
            note = {}
            if vault:
                note = _write_knowledge_note(
                    vault,
                    title=title,
                    source_path=pdf_path,
                    topic=topic,
                    pages_read=pages_read,
                    terms=terms,
                    memories=memories,
                    excerpts=excerpts,
                )

            stored = []
            if import_to_sqlite:
                for item in memories:
                    try:
                        memory = add_memory(
                            item.content,
                            category=item.category,
                            source="knowledge_pdf",
                            confidence=item.confidence,
                        )
                        if vault:
                            try:
                                mirror_memory_to_obsidian(memory)
                            except ObsidianMemoryError:
                                pass
                        payload = {
                            **memory_to_dict(memory),
                            "topic": topic.key,
                        }
                        stored.append(payload)
                        if memory.id not in imported_memory_ids:
                            imported_memory_ids.add(memory.id)
                            imported_memories.append(payload)
                    except MemoryStoreError as exc:
                        if len(errors) < 12:
                            errors.append(f"{pdf_path.name}: {exc}")

            documents.append(
                {
                    "title": title,
                    "source": pdf_path.relative_to(PROJECT_ROOT).as_posix(),
                    "topic": topic.label,
                    "topic_key": topic.key,
                    "pages_read": pages_read,
                    "terms": terms[:8],
                    "note_relative_path": note.get("relative_path", ""),
                    "memories": len(stored),
                }
            )
        except KnowledgeIngestionError as exc:
            if len(errors) < 12:
                errors.append(str(exc))

    index = {}
    if vault:
        index = _write_knowledge_index(vault, documents)

    embeddings: dict[str, object] = {"rebuilt": False}
    if imported_memories and rebuild_embeddings and settings.eva_embeddings_enabled:
        try:
            embeddings = {
                "rebuilt": True,
                **rebuild_memory_embeddings(limit=min(1000, max(300, len(imported_memories) + 200))),
            }
        except EmbeddingStoreError as exc:
            embeddings = {"rebuilt": False, "error": str(exc)}

    return {
        "source_dir": str(source),
        "documents_seen": len(pdfs),
        "imported_documents": len(documents),
        "imported_memories": len(imported_memories),
        "deleted_previous_notes": deleted_notes,
        "deleted_previous_memories": deleted_memories,
        "errors": errors,
        "documents": documents,
        "index": index,
        "embeddings": embeddings,
    }

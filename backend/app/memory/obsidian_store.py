import os
import json
import re
import time
import hashlib
import subprocess
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.config import settings
from app.memory.embedding_store import EmbeddingStoreError, rebuild_memory_embeddings
from app.memory.memory_store import (
    MemoryStoreError,
    add_memory,
    list_memories,
    memory_to_dict as sqlite_memory_to_dict,
)
from app.memory.profile_store import ProfileStoreError, load_profile
from app.projects.project_store import ProjectStoreError, load_projects


class ObsidianMemoryError(Exception):
    """Raised when Eva cannot read or write the local Obsidian memory vault."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FOLDERS = (
    "00 - Eva",
    "10 - Profile",
    "11 - Preferences",
    "12 - Creation",
    "20 - Memories",
    "30 - Projects",
    "40 - Daily",
    "50 - Operating Rules",
    "60 - Content",
    "70 - Templates",
    "80 - Learning",
    "90 - Inbox",
)

VAULT_INDEX_FILE = "00 - Eva/INDEX"
MANAGED_MARKER = "<!-- eva:managed -->"

IMPORT_SKIP_ROOTS = {
    ".obsidian",
    "00 - Eva",
    "20 - Memories",
    "40 - Daily",
    "70 - Templates",
}

IMPORT_CATEGORY_BY_ROOT = {
    "10 - Profile": "identity",
    "11 - Preferences": "preference",
    "12 - Creation": "creation",
    "30 - Projects": "project",
    "50 - Operating Rules": "operating_rule",
    "60 - Content": "content",
    "80 - Learning": "learning",
    "90 - Inbox": "idea",
}

SENSITIVE_IMPORT_MARKERS = (
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
    "clé secrète",
    "bearer ",
    "oauth",
)

PLACEHOLDER_IMPORT_MARKERS = (
    "ajoute ici",
    "a completer",
    "à compléter",
    "genere localement",
    "généré localement",
    "ce vault obsidian",
    "template",
    "{{",
    "}}",
    "source=",
    "ecris ici",
    "écris ici",
    "exemples a remplacer",
    "exemples à remplacer",
)


def _vault_path() -> Path:
    configured = Path(settings.eva_obsidian_vault_path)
    if configured.is_absolute():
        return configured
    return PROJECT_ROOT / configured


def _obsidian_app_config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", "")) / "obsidian"
    return Path.home() / ".config" / "obsidian"


def _obsidian_vault_id(vault: Path) -> str:
    return hashlib.sha1(str(vault.resolve()).encode("utf-8")).hexdigest()[:16]


def _obsidian_vault_name(vault: Path) -> str:
    return vault.name


def _register_obsidian_vault(vault: Path) -> dict[str, str]:
    config_dir = _obsidian_app_config_dir()
    if not str(config_dir).strip():
        return {"registered": "false", "reason": "appdata_missing"}

    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "obsidian.json"
    vault_id = _obsidian_vault_id(vault)
    now_ms = int(time.time() * 1000)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}

    vaults = payload.get("vaults")
    if not isinstance(vaults, dict):
        vaults = {}
    resolved_vault = str(vault.resolve())
    vaults = {
        key: value
        for key, value in vaults.items()
        if not (
            key != vault_id
            and isinstance(value, dict)
            and str(value.get("path", "")).lower() == resolved_vault.lower()
        )
    }
    vaults[vault_id] = {
        "path": resolved_vault,
        "ts": now_ms,
        "open": True,
    }
    payload["vaults"] = vaults
    config_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    window_state_path = config_dir / f"{vault_id}.json"
    _write_if_missing(
        window_state_path,
        json.dumps(
            {
                "x": 80,
                "y": 60,
                "width": 1280,
                "height": 850,
                "isMaximized": False,
                "devTools": False,
                "zoom": 0,
            },
            separators=(",", ":"),
        ),
    )

    return {
        "registered": "true",
        "vault_id": vault_id,
        "vault_name": _obsidian_vault_name(vault),
        "config_path": str(config_path),
    }


def _safe_filename(value: str, fallback: str = "general") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return cleaned or fallback


def _memory_to_dict(memory: Any) -> dict[str, Any]:
    if isinstance(memory, dict):
        return memory
    if is_dataclass(memory):
        return asdict(memory)
    return {
        "id": getattr(memory, "id", ""),
        "content": getattr(memory, "content", ""),
        "category": getattr(memory, "category", "general"),
        "created_at": getattr(memory, "created_at", ""),
        "source": getattr(memory, "source", "unknown"),
        "confidence": getattr(memory, "confidence", 1.0),
    }


def _write_if_missing(path: Path, content: str) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_generated(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{MANAGED_MARKER}\n{content}", encoding="utf-8")


def _seed_note_markdown(title: str, links: list[str], bullets: list[str]) -> str:
    lines = [
        f"# {title}",
        "",
        "> Note locale importable par Eva. Tu peux modifier, supprimer ou completer ces lignes dans Obsidian.",
        "",
    ]
    if links:
        lines.append("## Liens")
        for link in links:
            lines.append(f"- {link}")
        lines.append("")
    lines.append("## Memoires")
    lines.extend(f"- {bullet}" for bullet in bullets)
    lines.append("")
    return "\n".join(lines)


def _obsidian_seed_notes() -> dict[Path, str]:
    return {
        Path("11 - Preferences") / "Victor UX Taste.md": _seed_note_markdown(
            "Victor UX Taste",
            [
                "[[12 - Creation/Eva Product Vision]]",
                "[[50 - Operating Rules/Eva Autonomy Rules]]",
            ],
            [
                "#memory/preference Victor prefere une interface sombre, premium, sobre, avec bleu et cyan plutot que vert.",
                "#memory/preference Victor aime une direction Jarvis-like quand elle sert la clarte, pas des lignes HUD gratuites partout.",
                "#memory/preference Victor veut des animations utiles qui montrent la comprehension, les routes, l'execution et la verification.",
                "#memory/preference Victor n'aime pas les gros blocs de texte bruts jetes dans le chat.",
                "#memory/preference Victor prefere des reponses structurees en cartes, resumes courts, preuves et prochaines actions.",
                "#memory/preference Victor veut que le champ de chat reste visible et confortable sur desktop et mobile.",
                "#memory/preference Victor prefere Brave pour ouvrir les pages web depuis Eva.",
                "#memory/preference Victor veut une interface impressionnante mais logique, sans surcharge visuelle inutile.",
                "#memory/preference Victor aime les rendus de type centre de commande avec un coeur Eva, mais pas si cela empeche l'usage.",
                "#memory/preference Victor prefere que les boutons soient clairement cliquables et connectes a des actions reelles.",
            ],
        ),
        Path("11 - Preferences") / "Victor Working Preferences.md": _seed_note_markdown(
            "Victor Working Preferences",
            [
                "[[30 - Projects/Projects]]",
                "[[50 - Operating Rules/Eva Autonomy Rules]]",
            ],
            [
                "#memory/preference Victor veut qu'Eva comprenne l'intention avant de choisir un outil.",
                "#memory/preference Victor veut qu'Eva agisse quand une action locale non critique est possible, sans poser une question inutile.",
                "#memory/preference Victor veut qu'Eva annonce seulement les actions qu'elle a vraiment tentees ou verifiees.",
                "#memory/preference Victor veut des updates courts quand Eva travaille depuis Telegram.",
                "#memory/preference Victor prefere que les demandes floues soient resolues par contexte avant de demander une precision.",
                "#memory/preference Victor veut que F1, machine learning F1 et neural-network-F1 pointent vers le projet neural-network-F1 si le contexte colle.",
                "#memory/preference Victor veut qu'Eva garde le contexte d'une discussion Telegram au lieu de repartir de zero a chaque message.",
                "#memory/preference Victor veut que les recherches, lectures et ouvertures de pages soient executees directement quand elles sont utiles.",
                "#memory/preference Victor prefere les mails et posts clairs, directs, professionnels et pas trop longs.",
                "#memory/preference Victor veut qu'Eva evite les phrases de fin du type voulez-vous que je fasse autre chose quand une suite evidente existe.",
            ],
        ),
        Path("12 - Creation") / "Eva Product Vision.md": _seed_note_markdown(
            "Eva Product Vision",
            [
                "[[50 - Operating Rules/Eva Autonomy Rules]]",
                "[[30 - Projects/Eva Project Memory Seeds]]",
            ],
            [
                "#memory/creation Eva doit devenir un assistant personnel local gratuit, avec Ollama comme moteur IA local principal.",
                "#memory/creation Eva doit combiner memoire, outils locaux, vision ecran, skills et boucle cognitive.",
                "#memory/creation Eva doit fonctionner comme deuxieme cerveau operationnel de Victor, pas comme un simple chat.",
                "#memory/creation Eva doit apprendre des corrections de Victor et transformer les lecons stables en memoires ou regles.",
                "#memory/creation Eva doit utiliser Obsidian comme cerveau lisible et editable par Victor.",
                "#memory/creation Eva doit utiliser SQLite et embeddings locaux pour retrouver les souvenirs pertinents.",
                "#memory/creation Eva doit rester locale et gratuite par defaut, sans service cloud obligatoire.",
                "#memory/creation Eva doit savoir lancer des outils locaux, ouvrir des projets, preparer des prompts Cursor et verifier le resultat.",
                "#memory/creation Eva doit avoir un mode Telegram utile, avec contexte persistant et updates de travail.",
                "#memory/creation Eva doit verifier ses actions avec des preuves locales avant de parler comme si tout etait fait.",
            ],
        ),
        Path("30 - Projects") / "Eva Project Memory Seeds.md": _seed_note_markdown(
            "Eva Project Memory Seeds",
            [
                "[[12 - Creation/Eva Product Vision]]",
                "[[50 - Operating Rules/Eva Autonomy Rules]]",
            ],
            [
                "#memory/project Eva est le projet principal d'assistant local de Victor.",
                "#memory/project Eva doit evoluer par briques: memoire, brief, projets, messagerie, vision, skills, autonomie.",
                "#memory/project Pour creer un projet, Eva doit preparer un workspace, un brief, un README, des taches et un prompt Cursor.",
                "#memory/project Si GitHub CLI est disponible, Eva peut creer un repo GitHub pour un nouveau projet local.",
                "#memory/project Si cursor-agent est disponible, Eva peut lancer une session de codage autonome sur le projet cible.",
                "#memory/project Si cursor-agent manque, Eva doit diagnostiquer l'installation avant de demander un projet cible.",
                "#memory/project Quand Victor demande installer cursor agent pour tous les projets, la cible est l'environnement Eva et non un projet metier.",
                "#memory/project Quand Victor demande de continuer sur F1, Eva doit chercher neural-network-F1 dans les projets connus.",
                "#memory/project Quand Victor demande de travailler sur un projet flou, Eva doit classer les projets probables et choisir le meilleur match.",
                "#memory/project Eva doit relire le repo avant de proposer des ameliorations de code generiques.",
            ],
        ),
        Path("50 - Operating Rules") / "Eva Autonomy Rules.md": _seed_note_markdown(
            "Eva Autonomy Rules",
            [
                "[[50 - Operating Rules/Eva Operating Rules]]",
                "[[12 - Creation/Eva Product Vision]]",
            ],
            [
                "#memory/operating_rule Eva doit d'abord comprendre la demande, puis recuperer contexte, memoire et skills avant de repondre.",
                "#memory/operating_rule Eva doit distinguer demande de chat, action PC, mail, projet, recherche web, design, contenu et diagnostic.",
                "#memory/operating_rule Eva doit eviter de router vers Cursor quand la demande concerne Gmail, LinkedIn, une carte ou un site web.",
                "#memory/operating_rule Eva doit eviter les reponses du type je ne peux pas si une route locale ou un plan B existe.",
                "#memory/operating_rule Eva doit tenter les plans B autorises avant de conclure qu'une demande bloque.",
                "#memory/operating_rule Eva doit expliquer ce qui a ete tente seulement apres avoir tente une action reelle ou une verification.",
                "#memory/operating_rule Eva doit verifier qu'une page, app ou fichier est ouvert avant de dire que c'est ouvert.",
                "#memory/operating_rule Eva doit lire le contenu reel d'un mail avant de rediger une reponse.",
                "#memory/operating_rule Eva doit separer publicites, alertes automatiques, notifications et vrais mails humains.",
                "#memory/operating_rule Eva doit repondre dans la langue du mail source quand elle prepare un brouillon.",
                "#memory/operating_rule Eva doit ouvrir le mail ou le lien utile quand Victor demande de le voir.",
                "#memory/operating_rule Eva doit utiliser la vision ecran pour trouver un bouton si Victor ne donne pas de coordonnees.",
                "#memory/operating_rule Eva doit ouvrir Brave pour les pages web quand c'est disponible.",
                "#memory/operating_rule Eva doit garder une trace courte des actions et erreurs dans le journal operateur.",
                "#memory/operating_rule Eva doit eviter d'inventer des donnees Gmail, calendrier, LinkedIn ou web.",
                "#memory/operating_rule Eva doit demander une validation explicite uniquement pour les actions vraiment critiques.",
            ],
        ),
        Path("50 - Operating Rules") / "Eva Failure Recovery.md": _seed_note_markdown(
            "Eva Failure Recovery",
            [
                "[[50 - Operating Rules/Eva Autonomy Rules]]",
                "[[00 - Eva/Obsidian Memory Guide]]",
            ],
            [
                "#memory/operating_rule Si une route echoue, Eva doit analyser la cause, choisir une route alternative et executer le prochain essai autorise.",
                "#memory/operating_rule Si une recherche web ne trouve rien, Eva doit reformuler, changer de source ou ouvrir une page evidente.",
                "#memory/operating_rule Si une app ne s'ouvre pas, Eva doit tester une commande locale alternative ou ouvrir la version web.",
                "#memory/operating_rule Si Gmail ne donne pas le bon mail, Eva doit filtrer par sujet, expediteur, date et contexte avant de choisir.",
                "#memory/operating_rule Si le projet cible est ambigu, Eva doit faire du fuzzy matching sur les noms et descriptions.",
                "#memory/operating_rule Si la vision ecran est incertaine, Eva doit recapturer l'ecran avant de cliquer.",
                "#memory/operating_rule Si une action externe semble publier, envoyer ou supprimer, Eva doit s'arreter avant le clic final sauf cadre autorise.",
                "#memory/operating_rule Si Victor corrige Eva, Eva doit convertir la correction en regle ou preference si elle est stable.",
                "#memory/operating_rule Si Eva n'a pas assez de contexte, elle doit chercher dans les chats recents avant de demander une precision.",
                "#memory/operating_rule Si un outil repond failed, Eva doit presenter la prochaine piste concrete et non une excuse generique.",
            ],
        ),
        Path("60 - Content") / "DreamLense Content Memory.md": _seed_note_markdown(
            "DreamLense Content Memory",
            [
                "[[30 - Projects/DreamLense]]",
                "[[60 - Content/LinkedIn Strategy Memory]]",
            ],
            [
                "#memory/content DreamLense doit etre presente comme une solution de portraits professionnels generes par IA pour dirigeants, entrepreneurs et equipes.",
                "#memory/content Les posts DreamLense doivent parler du benefice business avant la technologie.",
                "#memory/content DreamLense doit garder un ton premium, clair, rassurant et professionnel.",
                "#memory/content Eviter les promesses exageres pour DreamLense; preferer des benefices concrets.",
                "#memory/content Un bon angle DreamLense: gagner du temps sur les portraits professionnels sans organiser de shooting.",
                "#memory/content Un bon angle DreamLense: coherences d'image pour equipes commerciales, dirigeants et profils LinkedIn.",
                "#memory/content Un bon angle DreamLense: image de marque personnelle plus nette et plus credible.",
                "#memory/content Un post DreamLense doit inclure un hook court, un probleme concret, un point de vue et une action douce.",
                "#memory/content Les visuels DreamLense doivent sembler premium, nets, humains et professionnels.",
                "#memory/content DreamLense ne doit pas etre vendu comme gadget IA mais comme outil d'image professionnelle.",
            ],
        ),
        Path("60 - Content") / "LinkedIn Strategy Memory.md": _seed_note_markdown(
            "LinkedIn Strategy Memory",
            [
                "[[60 - Content/DreamLense Content Memory]]",
                "[[11 - Preferences/Victor Working Preferences]]",
            ],
            [
                "#memory/content Victor veut des posts LinkedIn pertinents, pas du contenu generique.",
                "#memory/content Un post LinkedIn doit etre utile meme sans cliquer sur un lien.",
                "#memory/content Les idees LinkedIn doivent venir des signaux du matin, de DreamLense, de l'IA, du business ou de l'experience terrain.",
                "#memory/content Eva doit preparer le post, ouvrir LinkedIn si demande, mais verifier avant toute publication externe.",
                "#memory/content Pour LinkedIn, Eva doit privilegier exemples concrets, apprentissages et conseils actionnables.",
                "#memory/content Eviter les hashtags excessifs sur LinkedIn; preferer quelques tags pertinents si utiles.",
                "#memory/content Victor prefere un ton expert mais accessible sur LinkedIn.",
                "#memory/content Les posts LinkedIn DreamLense doivent eviter le jargon technique inutile.",
                "#memory/content Une idee LinkedIn utile peut venir d'un mail client, d'une actu IA ou d'un probleme repete par les prospects.",
                "#memory/content Eva doit distinguer brouillon LinkedIn, commentaire LinkedIn et analyse d'activite LinkedIn.",
            ],
        ),
        Path("80 - Learning") / "Eva Learning Loop.md": _seed_note_markdown(
            "Eva Learning Loop",
            [
                "[[20 - Memories/operating_rule]]",
                "[[50 - Operating Rules/Eva Failure Recovery]]",
                "[[90 - Inbox/Eva Learning Backlog]]",
            ],
            [
                "#memory/learning Eva doit apprendre par consolidation locale: extraire les lecons stables, les classer, les ajouter a SQLite, les miroir dans Obsidian, puis reconstruire les embeddings.",
                "#memory/learning Eva ne doit pas entrainer un nouveau modele sans dataset controle; elle doit utiliser embeddings, clusters, retrieval et reflexion locale.",
                "#memory/learning Eva doit convertir les erreurs repetees en regles courtes, pas stocker les conversations brutes.",
                "#memory/learning Eva doit garder les secrets hors Obsidian, hors SQLite et hors Git.",
                "#memory/learning Eva doit enrichir les clusters utiles: Victor, DreamLense, Gmail, projets code, design, screen navigation, messages et recovery.",
                "#memory/learning Eva doit privilegier les souvenirs actionnables: ce que Victor aime, ce qu'il refuse, les erreurs a ne pas refaire et les workflows qui marchent.",
                "#memory/learning Eva doit reconstruire les embeddings apres un gros enrichissement, mais pas a chaque message pour garder le chat rapide.",
                "#memory/learning Eva doit exposer les apprentissages dans Obsidian pour que Victor puisse corriger le cerveau local.",
            ],
        ),
        Path("90 - Inbox") / "Eva Learning Backlog.md": _seed_note_markdown(
            "Eva Learning Backlog",
            [
                "[[50 - Operating Rules/Eva Failure Recovery]]",
                "[[11 - Preferences/Victor Working Preferences]]",
            ],
            [
                "#memory/idea Eva doit progresser vers une boucle comprendre, contexte, planifier, agir, verifier, critiquer, reessayer, apprendre.",
                "#memory/idea Eva doit afficher sa decision comme une aide visuelle, mais l'action reelle reste prioritaire.",
                "#memory/idea Eva doit mieux gerer les prompts Telegram courts comme F1 en reliant au contexte precedent.",
                "#memory/idea Eva doit mieux resumer les mails importants et ignorer les pubs.",
                "#memory/idea Eva doit savoir ouvrir Spotify ou YouTube quand Victor demande une musique ou une video.",
                "#memory/idea Eva doit pouvoir ouvrir une carte utile dans le chat ou dans Brave selon la demande.",
                "#memory/idea Eva doit enrichir Obsidian avec les souvenirs stables et les liens entre projets, preferences et regles.",
                "#memory/idea Eva doit classer les erreurs repetitives pour apprendre a les resoudre plus vite.",
                "#memory/idea Eva doit eviter de rester bloquee sur un ancien contexte comme LinkedIn si Victor demande autre chose.",
                "#memory/idea Eva doit avoir un front plus calme, plus lisible, avec moins de lignes inutiles et plus de signal.",
            ],
        ),
    }


def _clean_display_text(value: object) -> str:
    text = str(value or "")
    replacements = {
        "\u00c3\u00a0": "a",
        "\u00c3\u00a2": "a",
        "\u00c3\u00a9": "e",
        "\u00c3\u00a8": "e",
        "\u00c3\u00aa": "e",
        "\u00c3\u00a7": "c",
        "\u00c3\u00b4": "o",
        "\u00e2\u20ac\u201c": "-",
        "\u2013": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _profile_markdown() -> str:
    try:
        profile = load_profile()
    except ProfileStoreError as exc:
        return f"# Profil Victor\n\nProfil indisponible: {exc}\n"

    identity = profile.get("identity", {}) if isinstance(profile, dict) else {}
    projects = profile.get("projects", []) if isinstance(profile, dict) else []
    writing = profile.get("writing_preferences", {}) if isinstance(profile, dict) else {}

    lines = [
        "# Profil Victor",
        "",
        "> Genere localement par Eva depuis `data/eva_profile.json`.",
        "",
    ]
    if isinstance(identity, dict):
        lines.append("## Identite")
        if identity.get("user_name"):
            lines.append(f"- Nom: {_clean_display_text(identity['user_name'])}")
        if identity.get("email"):
            lines.append(f"- Email: {_clean_display_text(identity['email'])}")
        lines.append("")

    if isinstance(projects, list) and projects:
        lines.append("## Projets")
        for project in projects:
            if not isinstance(project, dict):
                continue
            name = project.get("name", "Projet")
            clean_name = _clean_display_text(name)
            lines.append(f"### [[30 - Projects/{clean_name}|{clean_name}]]")
            for key in ("description", "website", "role"):
                if project.get(key):
                    lines.append(f"- {key}: {_clean_display_text(project[key])}")
            lines.append("")

    if isinstance(writing, dict) and writing:
        lines.append("## Preferences de redaction")
        if writing.get("style"):
            lines.append(f"- Style: {_clean_display_text(writing['style'])}")
        if writing.get("email_signature"):
            lines.append("")
            lines.append("```text")
            lines.append(_clean_display_text(writing["email_signature"]))
            lines.append("```")

    lines.extend(
        [
            "",
            "## Liens utiles",
            "",
            "- [[11 - Preferences/Creative Taste|Gouts creatifs]]",
            "- [[11 - Preferences/Working Preferences|Preferences de travail]]",
            "- [[12 - Creation/Creation DNA|ADN creation]]",
            "- [[60 - Content/LinkedIn Ideas|Idees LinkedIn]]",
        ]
    )

    return "\n".join(lines).strip() + "\n"


def _projects_markdown() -> str:
    try:
        projects = load_projects()
    except ProjectStoreError as exc:
        return f"# Projets Eva\n\nProjets indisponibles: {exc}\n"

    lines = [
        "# Projets Eva",
        "",
        "> Genere localement par Eva depuis `data/eva_projects.json`.",
        "",
    ]
    for project in projects:
        name = _clean_display_text(project["name"])
        lines.append(f"## [[30 - Projects/{name}|{name}]]")
        lines.append(f"- Chemin: `{project['path']}`")
        if project.get("description"):
            lines.append(f"- Description: {_clean_display_text(project['description'])}")
        if project.get("type"):
            lines.append(f"- Type: {_clean_display_text(project['type'])}")
        aliases = project.get("aliases", [])
        if aliases:
            lines.append(f"- Alias: {', '.join(str(alias) for alias in aliases)}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _project_detail_markdown(project: dict[str, Any]) -> str:
    name = _clean_display_text(project.get("name", "Projet"))
    description = _clean_display_text(project.get("description", ""))
    path = _clean_display_text(project.get("path", ""))
    aliases = project.get("aliases", [])
    aliases_text = ", ".join(_clean_display_text(alias) for alias in aliases) if aliases else ""
    lines = [
        f"# {name}",
        "",
        f"- Type: {_clean_display_text(project.get('type', 'code'))}",
        f"- Chemin: `{path}`" if path else "- Chemin: a completer",
        f"- Description: {description}" if description else "- Description: a completer",
    ]
    if aliases_text:
        lines.append(f"- Alias: {aliases_text}")
    lines.extend(
        [
            "",
            "## Role pour Eva",
            "",
            "- Comprendre le contexte du projet avant de proposer du code.",
            "- Lire la structure locale si le dossier est autorise.",
            "- Preparer des prompts Cursor/Codex contextualises quand elle ne peut pas coder directement.",
            "",
            "## Prochaines actions possibles",
            "",
            "- [[70 - Templates/Project Brief|Creer ou mettre a jour un brief projet]]",
            "- [[70 - Templates/Cursor Prompt|Preparer un prompt Cursor]]",
            "- [[50 - Operating Rules/Eva Operating Rules|Respecter les regles Eva]]",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _creative_taste_markdown() -> str:
    return "\n".join(
        [
            "# Creative Taste",
            "",
            "## Direction artistique que Victor aime",
            "",
            "- Interfaces premium, sombres, sobres, nettes.",
            "- Inspiration Jarvis / Iron Man: HUD, cartes techniques, cercles, radar, lignes lumineuses.",
            "- Bleu/cyan plutot que vert.",
            "- Sensation ChatGPT moderne pour le confort de chat, mais avec une couche visuelle Jarvis.",
            "- Animations utiles: progression, routes, hesitations, verification, pas de decoration gratuite.",
            "- Design qui montre ce qu'Eva comprend et ce qu'elle fait, sans jeter un bloc de texte brut.",
            "",
            "## A eviter",
            "",
            "- Blabla generique.",
            "- Interfaces trop plates ou mal alignees.",
            "- Gros textes non structures.",
            "- Boutons ou panneaux qui ne servent a rien.",
            "- Reponses qui demandent trop de confirmations pour des actions simples.",
            "",
            "## Liens",
            "",
            "- [[12 - Creation/Creation DNA]]",
            "- [[60 - Content/DreamLense Content Angles]]",
            "- [[70 - Templates/Frontend Brief]]",
        ]
    ).strip() + "\n"


def _working_preferences_markdown() -> str:
    return "\n".join(
        [
            "# Working Preferences",
            "",
            "## Style de collaboration",
            "",
            "- Victor veut qu'Eva comprenne l'intention avant de repondre.",
            "- Eva doit agir quand l'action est sure et locale, puis verifier.",
            "- Eva doit proposer un plan B si la premiere route echoue.",
            "- Eva ne doit pas demander une confirmation inutile pour une recherche, une ouverture d'app, un brief ou une lecture autorisee.",
            "- Eva doit etre concrete: resultat, preuve locale, prochaine action.",
            "",
            "## Ce qui frustre Victor",
            "",
            "- Repondre comme une IA sans outils alors qu'un outil local existe.",
            "- Inventer des mails, des donnees ou des pages ouvertes.",
            "- Ouvrir le mauvais mail ou le mauvais lien.",
            "- Dire qu'il manque un projet alors qu'un alias evident existe.",
            "- Demander 'voulez-vous autre chose' au lieu de continuer intelligemment.",
            "",
            "## Utilisation par Eva",
            "",
            "Quand Eva cree un mail, un post, un projet ou une interface, elle doit consulter cette note avec [[11 - Preferences/Creative Taste]] et [[50 - Operating Rules/Eva Operating Rules]].",
        ]
    ).strip() + "\n"


def _creation_dna_markdown() -> str:
    return "\n".join(
        [
            "# Creation DNA",
            "",
            "## Theme central",
            "",
            "Eva est le deuxieme cerveau operationnel de Victor: local, gratuit, connecte a ses outils, capable d'apprendre et d'agir.",
            "",
            "## Axes importants",
            "",
            "- Local-first avec Ollama.",
            "- Gratuit a l'usage: pas d'API OpenAI obligatoire, pas de cloud payant.",
            "- Memoire longue duree via SQLite + Obsidian.",
            "- Telegram comme bouche distante.",
            "- Hands desktop: ouvrir apps, navigateur, Spotify, Cursor, Obsidian.",
            "- Gmail/Calendar utiles, sans invention de donnees.",
            "- Project Factory: transformer une idee en workspace, repo, prompt, audit.",
            "",
            "## Quand Eva cree quelque chose",
            "",
            "- Toujours relier la creation aux gouts de Victor.",
            "- Produire un premier resultat utilisable, pas seulement une explication.",
            "- Garder une trace dans Obsidian si c'est une idee, une preference ou une lecon durable.",
        ]
    ).strip() + "\n"


def _dreamlense_markdown() -> str:
    return "\n".join(
        [
            "# DreamLense",
            "",
            "- Type: SAS specialisee dans les portraits professionnels generes par IA.",
            "- Site: https://dreamlense-ai.com",
            "- Role Victor: Directeur General.",
            "",
            "## Positionnement",
            "",
            "DreamLense aide les dirigeants, entrepreneurs, equipes commerciales et profils professionnels a obtenir des portraits premium sans shooting classique.",
            "",
            "## Angles utiles",
            "",
            "- Image de marque professionnelle.",
            "- Gain de temps.",
            "- Cohesion visuelle d'equipe.",
            "- Presence LinkedIn plus credible.",
            "- Portraits IA premium pour dirigeants et entrepreneurs.",
            "",
            "## Ton",
            "",
            "Clair, direct, premium, cordial. Eviter le jargon IA inutile.",
            "",
            "## Liens",
            "",
            "- [[60 - Content/DreamLense Content Angles]]",
            "- [[60 - Content/LinkedIn Ideas]]",
            "- [[70 - Templates/LinkedIn Post]]",
        ]
    ).strip() + "\n"


def _content_angles_markdown() -> str:
    return "\n".join(
        [
            "# DreamLense Content Angles",
            "",
            "## Posts LinkedIn possibles",
            "",
            "- Avant/apres: pourquoi une photo LinkedIn change la perception.",
            "- Portrait dirigeant: gagner en credibilite sans shooting complet.",
            "- Equipes commerciales: uniformiser les portraits pour inspirer confiance.",
            "- IA utile: pas remplacer l'humain, accelerer une presentation professionnelle.",
            "- Coulisses: comment obtenir un rendu premium avec peu de friction.",
            "",
            "## Hooks",
            "",
            "- Votre photo LinkedIn parle avant vous.",
            "- Un portrait professionnel n'est pas un detail de branding.",
            "- La premiere impression de votre equipe se joue souvent avant le premier appel.",
            "",
            "## CTA doux",
            "",
            "- Decouvrir DreamLense.",
            "- Tester un portrait professionnel IA.",
            "- Harmoniser les portraits de votre equipe.",
        ]
    ).strip() + "\n"


def _linkedin_ideas_markdown() -> str:
    return "\n".join(
        [
            "# LinkedIn Ideas",
            "",
            "## Idees recurrentes",
            "",
            "- Post educatif sur l'importance du portrait professionnel.",
            "- Post business sur la confiance dans un cycle de vente.",
            "- Post fondateur sur la construction de DreamLense.",
            "- Post comparaison: shooting classique vs portrait IA premium.",
            "- Post conseil: 5 erreurs de photo LinkedIn.",
            "",
            "## Regles",
            "",
            "- Pas de promesse exageree.",
            "- Montrer le benefice business avant la technologie.",
            "- Garder un ton premium, clair, utile.",
            "- Toujours verifier avant publication.",
        ]
    ).strip() + "\n"


def _template_markdown(title: str, body: str) -> str:
    return f"# {title}\n\n{body.strip()}\n"


def ensure_obsidian_vault() -> Path:
    vault = _vault_path()
    if not settings.eva_obsidian_memory_enabled:
        return vault

    try:
        vault.mkdir(parents=True, exist_ok=True)
        for folder in DEFAULT_FOLDERS:
            (vault / folder).mkdir(parents=True, exist_ok=True)

        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        _write_if_missing(
            obsidian_dir / "app.json",
            '{\n  "legacyEditor": false,\n  "livePreview": true\n}\n',
        )
        _write_if_missing(
            obsidian_dir / "appearance.json",
            '{\n  "theme": "obsidian",\n  "accentColor": "#54d7ff"\n}\n',
        )
        _write_if_missing(
            obsidian_dir / "graph.json",
            json.dumps(
                {
                    "collapse-filter": False,
                    "search": "",
                    "showTags": True,
                    "showAttachments": False,
                    "hideUnresolved": False,
                    "showOrphans": True,
                    "collapse-color-groups": False,
                    "colorGroups": [
                        {"query": "path:\"10 - Profile\"", "color": {"a": 1, "rgb": 5634047}},
                        {"query": "path:\"11 - Preferences\"", "color": {"a": 1, "rgb": 65535}},
                        {"query": "path:\"12 - Creation\"", "color": {"a": 1, "rgb": 2228223}},
                        {"query": "path:\"20 - Memories\"", "color": {"a": 1, "rgb": 65484}},
                        {"query": "path:\"30 - Projects\"", "color": {"a": 1, "rgb": 16755200}},
                        {"query": "path:\"60 - Content\"", "color": {"a": 1, "rgb": 16737792}},
                        {"query": "path:\"70 - Templates\"", "color": {"a": 1, "rgb": 8947967}},
                    ],
                    "collapse-display": False,
                    "showArrow": False,
                    "textFadeMultiplier": 0,
                    "nodeSizeMultiplier": 1,
                    "lineSizeMultiplier": 1,
                    "collapse-forces": False,
                    "centerStrength": 0.518713248970312,
                    "repelStrength": 10,
                    "linkStrength": 1,
                    "linkDistance": 250,
                    "scale": 1,
                    "close": False,
                },
                indent=2,
            )
            + "\n",
        )
        _write_if_missing(
            obsidian_dir / "hotkeys.json",
            json.dumps({"graph:open": [{"modifiers": ["Mod"], "key": "G"}]}, indent=2) + "\n",
        )

        readme_path = vault / "00 - Eva" / "README.md"
        if not readme_path.exists():
            readme_path.write_text(
                "\n".join(
                    [
                        "# Eva Memory Vault",
                        "",
                        "Ce vault Obsidian est local et ignore par Git.",
                        "Eva y miroir les souvenirs non sensibles pour les rendre lisibles et editables.",
                        "",
                        "Regles:",
                        "- pas de mots de passe;",
                        "- pas de tokens API;",
                        "- pas de secrets;",
                        "- les envois, publications et suppressions restent proteges;",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

        _write_generated(
            vault / "00 - Eva" / "INDEX.md",
            "\n".join(
                [
                    "# Eva Memory Vault",
                    "",
                    "## Navigation",
                    "",
                    "- [[10 - Profile/Victor|Profil Victor]]",
                    "- [[11 - Preferences/Creative Taste|Gouts creatifs]]",
                    "- [[11 - Preferences/Working Preferences|Preferences de travail]]",
                    "- [[12 - Creation/Creation DNA|ADN creation]]",
                    "- [[20 - Memories/general|Souvenirs generaux]]",
                    "- [[30 - Projects/Projects|Projets]]",
                    "- [[60 - Content/LinkedIn Ideas|Idees LinkedIn]]",
                    "- [[70 - Templates/Project Brief|Templates]]",
                    "- [[90 - Inbox/Memory Inbox|Inbox memoire editable]]",
                    "- [[00 - Eva/Obsidian Memory Guide|Guide memoire Obsidian]]",
                    "- [[50 - Operating Rules/Eva Operating Rules|Regles operatoires Eva]]",
                    "- [[40 - Daily|Journal quotidien]]",
                    "- Ouvre le graphe Obsidian avec `Ctrl+G` si la vue ne s'affiche pas deja.",
                    "",
                    "## Role du vault",
                    "",
                    "Ce coffre est le deuxieme cerveau lisible d'Eva: SQLite reste la source rapide, Obsidian sert a relire, corriger et enrichir les souvenirs.",
                    "",
                    "Eva lit un resume de ce vault dans son prompt local pour creer des mails, posts, projets, interfaces et plans plus alignes avec Victor.",
                    "",
                    "Les fichiers du coffre restent locaux et ignores par Git.",
                    "",
                ]
            ),
        )
        _write_generated(vault / "10 - Profile" / "Victor.md", _profile_markdown())
        _write_generated(vault / "11 - Preferences" / "Creative Taste.md", _creative_taste_markdown())
        _write_generated(vault / "11 - Preferences" / "Working Preferences.md", _working_preferences_markdown())
        _write_generated(vault / "12 - Creation" / "Creation DNA.md", _creation_dna_markdown())
        _write_generated(vault / "30 - Projects" / "Projects.md", _projects_markdown())
        try:
            for project in load_projects():
                project_name = _safe_filename(_clean_display_text(project.get("name", "project")), fallback="project")
                display_name = _clean_display_text(project.get("name", project_name))
                _write_generated(
                    vault / "30 - Projects" / f"{display_name}.md",
                    _project_detail_markdown(project),
                )
        except ProjectStoreError:
            pass
        _write_generated(vault / "30 - Projects" / "DreamLense.md", _dreamlense_markdown())
        _write_generated(vault / "60 - Content" / "DreamLense Content Angles.md", _content_angles_markdown())
        _write_generated(vault / "60 - Content" / "LinkedIn Ideas.md", _linkedin_ideas_markdown())
        _write_generated(
            vault / "00 - Eva" / "Obsidian Memory Guide.md",
            "\n".join(
                [
                    "# Obsidian Memory Guide",
                    "",
                    "## Comment rendre Eva plus personnelle",
                    "",
                    "1. Ecris une note manuelle dans [[90 - Inbox/Memory Inbox]].",
                    "2. Ou cree une note dans `11 - Preferences`, `12 - Creation`, `30 - Projects`, `50 - Operating Rules` ou `60 - Content`.",
                    "3. Dans Eva, ouvre `Memoire` puis clique `Importer notes Obsidian`.",
                    "4. Eva filtre les secrets, ajoute les souvenirs utiles dans SQLite, puis reconstruit les embeddings locaux si Ollama est disponible.",
                    "",
                    "## Format conseille",
                    "",
                    "- `#memory/preference J'aime les interfaces sombres, premium, avec un HUD bleu/cyan.`",
                    "- `#memory/project DreamLense doit garder un ton clair, direct et premium.`",
                    "- `#memory/operating_rule Eva doit verifier l'action locale avant d'annoncer qu'elle est faite.`",
                    "- `#memory/content Les posts LinkedIn DreamLense doivent parler du benefice business avant la technologie.`",
                    "",
                    "## Regles",
                    "",
                    "- Ne mets jamais de mot de passe, token, cle API ou secret dans Obsidian.",
                    "- Les notes generees par Eva sont lues comme contexte, mais les souvenirs importes viennent surtout de tes notes manuelles.",
                    "- Une ligne courte et concrete vaut mieux qu'un gros paragraphe vague.",
                    "",
                ]
            ),
        )
        _write_generated(
            vault / "70 - Templates" / "Project Brief.md",
            _template_markdown(
                "Project Brief",
                """
## Contexte

- Idee:
- Utilisateur cible:
- Probleme:
- Resultat attendu:

## V1

- Fonctionnalites indispensables:
- Stack pressentie:
- Fichiers a creer:
- Donnees locales:

## Definition of done

- L'app se lance.
- Le README explique l'installation.
- Les risques/secrets sont documentes.
- Eva peut auditer le resultat.
""",
            ),
        )
        _write_generated(
            vault / "70 - Templates" / "Cursor Prompt.md",
            _template_markdown(
                "Cursor Prompt",
                """
Tu travailles dans le projet: {{project_name}}.

Objectif:
{{objective}}

Contraintes:
- respecter l'architecture existante;
- garder le code simple et maintenable;
- ne pas ajouter de service payant obligatoire;
- verifier avec les tests ou un build;
- resumer les fichiers modifies.

Contexte Victor:
- style direct, utile, premium;
- interfaces sombres, Jarvis-like, bleu/cyan;
- autonomie locale et preuves d'action.
""",
            ),
        )
        _write_generated(
            vault / "70 - Templates" / "Email Reply.md",
            _template_markdown(
                "Email Reply",
                """
## Regles

- Lire le mail reel avant de rediger.
- Detecter la langue du mail.
- Repondre dans la meme langue.
- Utiliser la signature de Victor si pertinent.
- Ne pas inventer de fait, prix, rendez-vous ou engagement.
- Si c'est sensible ou ambigu: brouillon uniquement.

## Structure

Bonjour,

{{reponse_claire}}

{{signature}}
""",
            ),
        )
        _write_generated(
            vault / "70 - Templates" / "LinkedIn Post.md",
            _template_markdown(
                "LinkedIn Post",
                """
## Forme

Hook court.

Probleme concret.

Observation / point de vue.

Solution ou conseil.

CTA doux.

## Style

- clair;
- premium;
- pas de jargon IA inutile;
- utile pour dirigeants, entrepreneurs ou equipes commerciales.
""",
            ),
        )
        _write_generated(
            vault / "70 - Templates" / "Morning Brief.md",
            _template_markdown(
                "Morning Brief",
                """
## Sortie attendue

1. 3 choses a savoir.
2. 1 opportunite business.
3. 1 risque ou tendance a surveiller.
4. 1 idee LinkedIn.
5. 1 action proposee.

## Filtres Victor

- IA;
- business;
- finance;
- DreamLense;
- productivite;
- signaux LinkedIn/Gmail utiles.
""",
            ),
        )
        _write_generated(
            vault / "70 - Templates" / "Frontend Brief.md",
            _template_markdown(
                "Frontend Brief",
                """
## Direction

Interface sombre, premium, Jarvis-like, avec bleu/cyan.

## Exigences

- Information structuree, pas de gros texte brut.
- Animations utiles pour montrer comprehension, routes et verification.
- Input toujours visible.
- Sidebar lisible.
- Responsive mobile.
- Pas d'elements visuels gratuits si cela nuit a l'usage.
""",
            ),
        )
        _write_if_missing(
            vault / "90 - Inbox" / "Ideas Inbox.md",
            "# Ideas Inbox\n\nAjoute ici les idees brutes que Victor veut transformer en projet, post ou tache.\n",
        )
        _write_if_missing(
            vault / "90 - Inbox" / "Memory Inbox.md",
            "\n".join(
                [
                    "# Memory Inbox",
                    "",
                    "Ecris ici les souvenirs que tu veux donner a Eva, puis clique `Importer notes Obsidian` dans le panneau Memoire.",
                    "",
                    "Exemples a remplacer:",
                    "",
                    "- #memory/preference J'aime les interfaces Jarvis-like, sombres, premium, avec du bleu/cyan.",
                    "- #memory/project DreamLense doit rester clair, direct, premium et oriente business.",
                    "- #memory/operating_rule Eva doit lire le contenu reel avant de rediger une reponse.",
                    "",
                ]
            ),
        )
        _write_if_missing(
            vault / "50 - Operating Rules" / "Eva Operating Rules.md",
            "\n".join(
                [
                    "# Eva Operating Rules",
                    "",
                    "- Comprendre l'objectif avant d'agir.",
                    "- Chercher dans la memoire et les projets avant de dire qu'une information manque.",
                    "- Ne pas inventer une action: chaque action annoncee doit avoir une preuve locale.",
                    "- Continuer avec un plan B quand une etape bloque.",
                    "- Ne jamais stocker de mot de passe, token ou secret.",
                    "- Ne jamais envoyer, publier ou supprimer sans cadre explicite et sur.",
                    "",
                ]
            ),
        )
    except OSError as exc:
        raise ObsidianMemoryError("Impossible d'initialiser le vault Obsidian local.") from exc

    return vault


def obsidian_open_uri() -> str:
    vault = _vault_path()
    return (
        "obsidian://open?"
        f"vault={quote(_obsidian_vault_name(vault))}"
        f"&file={quote(VAULT_INDEX_FILE, safe='')}"
    )


def obsidian_path_open_uri() -> str:
    index_path = _vault_path().resolve() / "00 - Eva" / "INDEX.md"
    return f"obsidian://open?path={quote(str(index_path))}"


def _read_note_excerpt(path: Path, max_chars: int = 1000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.replace(MANAGED_MARKER, "").strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n..."
    return text


def _query_has_any(query: str, markers: tuple[str, ...]) -> bool:
    normalized = query.lower()
    return any(marker in normalized for marker in markers)


@dataclass(frozen=True)
class ObsidianMemoryCandidate:
    content: str
    category: str
    note_path: str
    confidence: float


def _normalize_import_text(text: str) -> str:
    return " ".join(_clean_display_text(text).lower().strip().split())


def _note_root(relative_path: Path) -> str:
    return relative_path.parts[0] if relative_path.parts else ""


def _is_managed_note(text: str) -> bool:
    return text.lstrip().startswith(MANAGED_MARKER)


def _is_importable_note(note_path: Path, vault: Path) -> bool:
    try:
        relative = note_path.relative_to(vault)
    except ValueError:
        return False

    root = _note_root(relative)
    if root in IMPORT_SKIP_ROOTS:
        return False
    if any(part.startswith(".") for part in relative.parts):
        return False
    return note_path.suffix.lower() == ".md"


def _category_from_note(relative_path: Path, text: str) -> str:
    tag_match = re.search(r"#(?:memory|memoire)/([a-zA-Z0-9_-]+)", text, flags=re.IGNORECASE)
    if tag_match:
        return re.sub(r"[^a-zA-Z0-9_-]", "", tag_match.group(1).lower()) or "obsidian"
    return IMPORT_CATEGORY_BY_ROOT.get(_note_root(relative_path), "obsidian")


def _strip_markdown_memory_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^[-*+]\s+", "", cleaned)
    cleaned = re.sub(r"^\d+[.)]\s+", "", cleaned)
    cleaned = re.sub(r"^\[[ xX]\]\s+", "", cleaned)
    cleaned = re.sub(r"#(?:memory|memoire)/[a-zA-Z0-9_-]+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"#(?:eva-memory|memoire-eva|memory|memoire)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", cleaned)
    cleaned = re.sub(r"\[\[([^\]]+)\]\]", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    return " ".join(cleaned.split())


def _should_import_candidate(text: str) -> bool:
    normalized = _normalize_import_text(text)
    if len(text) < 12 or len(text) > 560:
        return False
    if normalized.endswith(":"):
        return False
    if normalized.startswith(("#", ">", "---")):
        return False
    if re.fullmatch(r"https?://\S+", normalized):
        return False
    if any(marker in normalized for marker in SENSITIVE_IMPORT_MARKERS):
        return False
    if any(marker in normalized for marker in PLACEHOLDER_IMPORT_MARKERS):
        return False
    if "| #" in text and "source=" in normalized:
        return False
    return True


def _prefix_with_note_context(note_path: Path, relative_path: Path, text: str) -> str:
    root = _note_root(relative_path)
    if root in {"30 - Projects", "60 - Content"}:
        note_title = note_path.stem.strip()
        if note_title and note_title.lower() not in text.lower():
            return f"{note_title}: {text}"
    return text


def _extract_obsidian_memory_candidates(note_path: Path, vault: Path) -> list[ObsidianMemoryCandidate]:
    try:
        relative_path = note_path.relative_to(vault)
        raw_text = note_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return []

    if _is_managed_note(raw_text):
        return []

    candidates: list[ObsidianMemoryCandidate] = []
    paragraph: list[str] = []
    in_code_block = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        raw_candidate = " ".join(paragraph)
        paragraph.clear()
        cleaned = _strip_markdown_memory_line(raw_candidate)
        if not _should_import_candidate(cleaned):
            return
        content = _prefix_with_note_context(note_path, relative_path, cleaned)
        candidates.append(
            ObsidianMemoryCandidate(
                content=content,
                category=_category_from_note(relative_path, raw_candidate),
                note_path=relative_path.as_posix(),
                confidence=0.84,
            )
        )

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        line_lower = line.lower()
        if line.startswith("```"):
            flush_paragraph()
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if not line:
            flush_paragraph()
            continue
        if line.startswith(("# ", "## ", "### ", "#### ", "---")):
            flush_paragraph()
            continue
        if re.match(r"^[-*+]|\d+[.)]\s+", line):
            flush_paragraph()
            if "[[" in line and "#memory/" not in line_lower and "#memoire/" not in line_lower:
                continue
            cleaned = _strip_markdown_memory_line(line)
            if not _should_import_candidate(cleaned):
                continue
            content = _prefix_with_note_context(note_path, relative_path, cleaned)
            candidates.append(
                ObsidianMemoryCandidate(
                    content=content,
                    category=_category_from_note(relative_path, line),
                    note_path=relative_path.as_posix(),
                    confidence=0.88 if "#memory/" in line.lower() or "#memoire/" in line.lower() else 0.8,
                )
            )
            continue
        paragraph.append(line)

    flush_paragraph()
    return candidates


def _obsidian_note_inventory(vault: Path) -> dict[str, int]:
    markdown_files = list(vault.rglob("*.md")) if vault.exists() else []
    managed_notes = 0
    importable_notes = 0
    for note_path in markdown_files:
        try:
            raw_text = note_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _is_managed_note(raw_text):
            managed_notes += 1
        if _is_importable_note(note_path, vault) and not _is_managed_note(raw_text):
            importable_notes += 1

    return {
        "markdown_files": len(markdown_files),
        "managed_notes": managed_notes,
        "manual_notes": max(0, len(markdown_files) - managed_notes),
        "importable_notes": importable_notes,
    }


def import_obsidian_notes_to_memories(limit: int = 200, rebuild_index: bool = False) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        return {
            "enabled": False,
            "imported": 0,
            "candidates": 0,
            "path": str(_vault_path()),
        }

    vault = ensure_obsidian_vault()
    safe_limit = min(max(int(limit), 1), 1000)
    imported: list[dict[str, Any]] = []
    failures: list[str] = []
    candidates: list[ObsidianMemoryCandidate] = []
    scanned_files = 0
    skipped_files = 0

    try:
        existing_contents = {
            _normalize_import_text(memory.content)
            for memory in list_memories(limit=200)
        }
    except MemoryStoreError:
        existing_contents = set()

    for note_path in sorted(vault.rglob("*.md")):
        if not _is_importable_note(note_path, vault):
            skipped_files += 1
            continue
        scanned_files += 1
        extracted = _extract_obsidian_memory_candidates(note_path, vault)
        for candidate in extracted:
            if len(candidates) >= safe_limit:
                break
            normalized = _normalize_import_text(candidate.content)
            if normalized in existing_contents:
                continue
            candidates.append(candidate)
            existing_contents.add(normalized)
        if len(candidates) >= safe_limit:
            break

    for candidate in candidates:
        try:
            memory = add_memory(
                candidate.content,
                category=candidate.category,
                source="obsidian",
                confidence=candidate.confidence,
            )
            imported.append(
                {
                    **sqlite_memory_to_dict(memory),
                    "note_path": candidate.note_path,
                }
            )
        except MemoryStoreError as exc:
            if len(failures) < 8:
                failures.append(f"{candidate.note_path}: {exc}")

    embeddings: dict[str, object] = {"rebuilt": False}
    if imported and rebuild_index and settings.eva_embeddings_enabled:
        try:
            embeddings = {
                "rebuilt": True,
                **rebuild_memory_embeddings(limit=min(1000, max(250, len(imported) + 200))),
            }
        except EmbeddingStoreError as exc:
            embeddings = {
                "rebuilt": False,
                "error": str(exc),
            }

    return {
        "enabled": True,
        "path": str(vault),
        "scanned_files": scanned_files,
        "skipped_files": skipped_files,
        "candidates": len(candidates),
        "imported": len(imported),
        "failed": len(failures),
        "failures": failures,
        "memories": imported[:40],
        "embeddings": embeddings,
    }


def seed_obsidian_memory_vault(
    import_to_sqlite: bool = True,
    limit: int = 500,
    rebuild_index: bool = False,
) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        return {
            "enabled": False,
            "seeded": 0,
            "existing": 0,
            "path": str(_vault_path()),
        }

    vault = ensure_obsidian_vault()
    seeded: list[str] = []
    existing: list[str] = []
    errors: list[str] = []

    for relative_path, content in _obsidian_seed_notes().items():
        note_path = vault / relative_path
        try:
            if note_path.exists():
                existing.append(relative_path.as_posix())
                continue
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(content, encoding="utf-8")
            seeded.append(relative_path.as_posix())
        except OSError as exc:
            if len(errors) < 8:
                errors.append(f"{relative_path.as_posix()}: {exc}")

    inventory = _obsidian_note_inventory(vault)
    import_result: dict[str, Any] | None = None
    if import_to_sqlite:
        import_result = import_obsidian_notes_to_memories(limit=limit, rebuild_index=rebuild_index)

    return {
        "enabled": True,
        "path": str(vault),
        "seeded": len(seeded),
        "existing": len(existing),
        "errors": errors,
        "notes": seeded,
        "existing_notes": existing,
        "markdown_files": inventory["markdown_files"],
        "importable_notes": inventory["importable_notes"],
        "import": import_result,
    }


def build_obsidian_prompt_context(query: str, max_chars: int = 6500) -> str:
    if not settings.eva_obsidian_memory_enabled:
        return "Contexte Obsidian: desactive."

    vault = ensure_obsidian_vault()
    note_paths = [
        vault / "10 - Profile" / "Victor.md",
        vault / "11 - Preferences" / "Creative Taste.md",
        vault / "11 - Preferences" / "Working Preferences.md",
        vault / "12 - Creation" / "Creation DNA.md",
        vault / "50 - Operating Rules" / "Eva Operating Rules.md",
    ]

    if _query_has_any(query, ("dreamlense", "linkedin", "post", "contenu", "prospect")):
        note_paths.extend(
            [
                vault / "30 - Projects" / "DreamLense.md",
                vault / "60 - Content" / "DreamLense Content Angles.md",
                vault / "60 - Content" / "LinkedIn Ideas.md",
                vault / "70 - Templates" / "LinkedIn Post.md",
            ]
        )

    if _query_has_any(query, ("projet", "repo", "github", "cursor", "codex", "code", "f1")):
        note_paths.extend(
            [
                vault / "30 - Projects" / "Projects.md",
                vault / "70 - Templates" / "Project Brief.md",
                vault / "70 - Templates" / "Cursor Prompt.md",
            ]
        )

    if _query_has_any(query, ("mail", "email", "gmail", "reponse", "relance")):
        note_paths.append(vault / "70 - Templates" / "Email Reply.md")

    if _query_has_any(query, ("brief", "news", "actu", "veille", "rss")):
        note_paths.append(vault / "70 - Templates" / "Morning Brief.md")

    if _query_has_any(query, ("frontend", "design", "interface", "ui", "site", "app")):
        note_paths.append(vault / "70 - Templates" / "Frontend Brief.md")

    seen: set[Path] = set()
    sections = [
        "Contexte Obsidian local de Victor.",
        "Ces notes sont locales et editables dans Obsidian. Utilise-les pour mieux creer, rediger et decider. N'invente pas au-dela des notes.",
    ]
    for note_path in note_paths:
        resolved = note_path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        excerpt = _read_note_excerpt(note_path)
        if not excerpt:
            continue
        relative = note_path.relative_to(vault).as_posix()
        block = f"\n---\nNote: {relative}\n{excerpt}"
        if sum(len(section) for section in sections) + len(block) > max_chars:
            break
        sections.append(block)

    return "\n".join(sections)


def hydrate_obsidian_vault() -> dict[str, Any]:
    vault = ensure_obsidian_vault()
    inventory = _obsidian_note_inventory(vault)
    return {
        "hydrated": True,
        "path": str(vault),
        "markdown_files": inventory["markdown_files"],
        "manual_notes": inventory["manual_notes"],
        "managed_notes": inventory["managed_notes"],
        "importable_notes": inventory["importable_notes"],
        "key_notes": [
            "11 - Preferences/Creative Taste.md",
            "11 - Preferences/Working Preferences.md",
            "12 - Creation/Creation DNA.md",
            "60 - Content/DreamLense Content Angles.md",
            "60 - Content/LinkedIn Ideas.md",
            "70 - Templates/Project Brief.md",
            "70 - Templates/Cursor Prompt.md",
            "70 - Templates/Email Reply.md",
            "70 - Templates/LinkedIn Post.md",
            "70 - Templates/Frontend Brief.md",
            "80 - Learning/Eva Learning Loop.md",
        ],
    }


def _open_obsidian_graph_view() -> None:
    if os.name != "nt":
        return

    script = r"""
$shell = New-Object -ComObject WScript.Shell
Start-Sleep -Seconds 3
$null = $shell.AppActivate('Obsidian')
Start-Sleep -Milliseconds 500
$shell.SendKeys('^g')
Start-Sleep -Seconds 1
$shell.SendKeys('^p')
Start-Sleep -Milliseconds 300
$shell.SendKeys('Open graph view')
Start-Sleep -Milliseconds 300
$shell.SendKeys('{ENTER}')
"""
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def _obsidian_exe_path() -> Path | None:
    if os.name != "nt":
        return None

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Obsidian" / "Obsidian.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Obsidian" / "Obsidian.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Obsidian" / "Obsidian.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def obsidian_status() -> dict[str, Any]:
    vault = _vault_path()
    inventory = _obsidian_note_inventory(vault)
    return {
        "enabled": settings.eva_obsidian_memory_enabled,
        "path": str(vault),
        "exists": vault.exists(),
        "markdown_files": inventory["markdown_files"],
        "manual_notes": inventory["manual_notes"],
        "managed_notes": inventory["managed_notes"],
        "importable_notes": inventory["importable_notes"],
        "import_supported": True,
        "brain_hydrated": (vault / "12 - Creation" / "Creation DNA.md").exists()
        and (vault / "11 - Preferences" / "Creative Taste.md").exists(),
        "open_uri": obsidian_open_uri(),
        "path_open_uri": obsidian_path_open_uri(),
        "vault_name": _obsidian_vault_name(vault),
        "vault_id": _obsidian_vault_id(vault),
        "app_config_dir": str(_obsidian_app_config_dir()),
        "folders": [
            {
                "name": folder,
                "exists": (vault / folder).exists(),
            }
            for folder in DEFAULT_FOLDERS
        ],
        "git_ignored": True,
    }


def open_obsidian_vault(open_graph: bool = True) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        raise ObsidianMemoryError("La memoire Obsidian est desactivee.")

    vault = ensure_obsidian_vault()
    registration = _register_obsidian_vault(vault)
    uri = obsidian_open_uri()
    open_method = "uri"
    try:
        if os.name == "nt":
            obsidian_exe = _obsidian_exe_path()
            if obsidian_exe:
                subprocess.Popen(
                    [str(obsidian_exe), str(vault.resolve())],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                open_method = "exe_path"
            else:
                os.startfile(uri)  # type: ignore[attr-defined]
        elif os.environ.get("XDG_CURRENT_DESKTOP"):
            subprocess.Popen(["xdg-open", uri])
        else:
            subprocess.Popen(["open", uri])
    except Exception as exc:
        raise ObsidianMemoryError(
            f"Impossible d'ouvrir Obsidian automatiquement. Ouvre ce dossier dans Obsidian: {vault}"
        ) from exc

    if open_graph:
        _open_obsidian_graph_view()

    return {
        "opened": True,
        "path": str(vault),
        "open_uri": uri,
        "open_method": open_method,
        "registration": registration,
        "graph_requested": open_graph,
    }


def _append_to_file(path: Path, header: str, block: str) -> None:
    if not path.exists():
        path.write_text(f"{header}\n\n", encoding="utf-8")

    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{block}\n")


def _already_contains_memory(path: Path, memory_id: object) -> bool:
    if not memory_id or not path.exists():
        return False
    marker = f"| #{memory_id} |"
    return marker in path.read_text(encoding="utf-8", errors="replace")


def mirror_memory_to_obsidian(memory: Any) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        return {"mirrored": False, "reason": "disabled"}

    vault = ensure_obsidian_vault()
    payload = _memory_to_dict(memory)
    content = str(payload.get("content", "")).strip()
    if not content:
        return {"mirrored": False, "reason": "empty"}

    category = _safe_filename(str(payload.get("category", "general")))
    memory_id = payload.get("id", "")
    source = payload.get("source", "unknown")
    confidence = payload.get("confidence", 1.0)
    created_at = payload.get("created_at") or datetime.now(UTC).isoformat()

    block = "\n".join(
        [
            f"- {created_at} | #{memory_id} | source={source} | confidence={confidence}",
            f"  - {content}",
        ]
    )

    try:
        memory_path = vault / "20 - Memories" / f"{category}.md"
        if _already_contains_memory(memory_path, memory_id):
            return {
                "mirrored": False,
                "reason": "already_present",
                "path": str(memory_path),
            }
        _append_to_file(memory_path, f"# Memories - {category}", block)

        daily_path = vault / "40 - Daily" / f"{datetime.now().date().isoformat()}.md"
        if not _already_contains_memory(daily_path, memory_id):
            _append_to_file(daily_path, f"# Journal Eva - {datetime.now().date().isoformat()}", block)
    except OSError as exc:
        raise ObsidianMemoryError("Impossible d'ecrire dans le vault Obsidian local.") from exc

    return {
        "mirrored": True,
        "path": str(memory_path),
    }


def sync_memories_to_obsidian(memories: list[Any]) -> dict[str, Any]:
    if not settings.eva_obsidian_memory_enabled:
        return {
            "synced": 0,
            "enabled": False,
            "path": str(_vault_path()),
        }

    ensure_obsidian_vault()
    synced = 0
    for memory in memories:
        result = mirror_memory_to_obsidian(memory)
        if result.get("mirrored"):
            synced += 1

    return {
        "synced": synced,
        "enabled": True,
        "path": str(_vault_path()),
    }

from dataclasses import dataclass

from app.security.action_policy import ActionPolicyLevel


@dataclass(frozen=True)
class ToolDescriptor:
    key: str
    label: str
    category: str
    policy_level: ActionPolicyLevel
    description: str
    enabled: bool = True


TOOLS = (
    ToolDescriptor(
        key="ollama_chat",
        label="Ollama Chat",
        category="llm",
        policy_level="read_only",
        description="Reponses IA locales via Ollama.",
    ),
    ToolDescriptor(
        key="memory_store",
        label="Memoire locale",
        category="memory",
        policy_level="read_only",
        description="Lecture et ajout prudent de souvenirs non sensibles.",
    ),
    ToolDescriptor(
        key="hybrid_memory_router",
        label="Routeur memoire",
        category="memory",
        policy_level="read_only",
        description="Route les demandes vers clusters + FTS/BM25 + embeddings Ollama locaux.",
    ),
    ToolDescriptor(
        key="obsidian_memory",
        label="Obsidian Memory",
        category="memory",
        policy_level="read_only",
        description="Miroir Markdown local des souvenirs Eva dans un vault Obsidian ignore par Git.",
    ),
    ToolDescriptor(
        key="skills_registry",
        label="Skills Eva",
        category="skills",
        policy_level="read_only",
        description="Catalogue local de competences qui oriente les reponses d'Eva.",
    ),
    ToolDescriptor(
        key="action_planner",
        label="Planificateur d'action",
        category="agents",
        policy_level="read_only",
        description="Boucle interne comprendre, router, choisir l'outil, verifier la securite puis executer.",
    ),
    ToolDescriptor(
        key="understanding_layer",
        label="Couche comprehension",
        category="agents",
        policy_level="read_only",
        description="Interprete chaque message avant reponse ou action, avec domaine, objectif, preuves et outil prefere.",
    ),
    ToolDescriptor(
        key="operator_journal",
        label="Journal operateur",
        category="agents",
        policy_level="read_only",
        description="Trace les demandes, decisions, resultats et reflexes de relance pour ameliorer l'autonomie locale.",
    ),
    ToolDescriptor(
        key="autonomous_job_runner",
        label="Job Runner autonome",
        category="agents",
        policy_level="draft_only",
        description="Queue locale JSONL avec execution un job a la fois, resultats sauvegardes, checkpoints et reprise au redemarrage.",
    ),
    ToolDescriptor(
        key="file_read",
        label="Lecture fichiers",
        category="files",
        policy_level="read_only",
        description="Lecture texte dans les dossiers autorises.",
    ),
    ToolDescriptor(
        key="rust_project_indexer",
        label="Rust Project Indexer",
        category="files",
        policy_level="read_only",
        description="Sidecar Rust optionnel pour scanner rapidement les projets et produire un index JSON local.",
    ),
    ToolDescriptor(
        key="web_search",
        label="Recherche web",
        category="web",
        policy_level="read_only",
        description="Recherche web gratuite sans API payante.",
    ),
    ToolDescriptor(
        key="browser_video_assist",
        label="Video / navigateur",
        category="web",
        policy_level="draft_only",
        description="Ouvre Brave ou YouTube quand un support web/video aide mieux que du texte.",
    ),
    ToolDescriptor(
        key="spotify_local",
        label="Spotify local",
        category="media",
        policy_level="draft_only",
        description="Ouvre Spotify, lance une recherche musicale et tente le controle clavier/souris local.",
    ),
    ToolDescriptor(
        key="desktop_automation",
        label="Hands desktop",
        category="system",
        policy_level="draft_only",
        description="Clics pixels, touches media et clavier local pour piloter le PC sans API externe.",
    ),
    ToolDescriptor(
        key="visual_action",
        label="Vision action",
        category="system",
        policy_level="draft_only",
        description="Regarde l'ecran avec Ollama vision, trouve un bouton/champ et agit sans coordonnees manuelles.",
    ),
    ToolDescriptor(
        key="screen_navigator",
        label="Navigation ecran",
        category="system",
        policy_level="draft_only",
        description="Boucle observer, choisir, cliquer/coller/ouvrir, puis verifier pour naviguer dans l'UI locale.",
    ),
    ToolDescriptor(
        key="screen_training_autopilot",
        label="Autopilote entrainement",
        category="system",
        policy_level="draft_only",
        description="Boucle visuelle longue pour exercices non officiels: observer, cliquer, verifier et continuer.",
    ),
    ToolDescriptor(
        key="beeper_assistant",
        label="Beeper",
        category="messaging",
        policy_level="draft_only",
        description="Ouvre Beeper, lit les messages visibles via vision locale et prepare des reponses sans envoyer.",
    ),
    ToolDescriptor(
        key="cursor_prompt",
        label="Prompt Cursor",
        category="code",
        policy_level="draft_only",
        description="Preparation de prompts Cursor/Codex sans appel OpenAI par Eva.",
    ),
    ToolDescriptor(
        key="cursor_agent_setup",
        label="Setup Cursor Agent",
        category="code",
        policy_level="draft_only",
        description="Verifie et installe Cursor Agent CLI via Windows WSL quand Eva est appelee depuis un canal fiable.",
    ),
    ToolDescriptor(
        key="project_factory",
        label="Project Factory",
        category="code",
        policy_level="draft_only",
        description="Prepare et peut lancer un workspace, un prompt Cursor, un commit local et un repo GitHub en mode operator.",
    ),
    ToolDescriptor(
        key="google_stitch_bridge",
        label="Google Stitch",
        category="design",
        policy_level="draft_only",
        description="Prepare un brief UI pour Google Stitch, le copie dans le presse-papiers et ouvre Stitch dans Brave.",
    ),
    ToolDescriptor(
        key="gmail_reply_draft",
        label="Brouillon Gmail",
        category="gmail",
        policy_level="draft_only",
        description="Brouillon de reponse email, aucun envoi automatique.",
    ),
    ToolDescriptor(
        key="gmail_auto_reply",
        label="Auto-reponse Gmail",
        category="gmail",
        policy_level="confirmation_required",
        description="Envoie seulement les reponses evidentes, non sensibles et similaires aux anciens mails envoyes.",
    ),
    ToolDescriptor(
        key="linkedin_draft",
        label="LinkedIn",
        category="linkedin",
        policy_level="draft_only",
        description="Idees, posts et commentaires LinkedIn en brouillon uniquement.",
    ),
    ToolDescriptor(
        key="linkedin_browser_bridge",
        label="LinkedIn Browser",
        category="linkedin",
        policy_level="draft_only",
        description="Copie un post LinkedIn dans le presse-papiers et ouvre LinkedIn localement sans API.",
    ),
    ToolDescriptor(
        key="heartbeat",
        label="Heartbeat",
        category="automation",
        policy_level="read_only",
        description="Taches locales planifiees et controles de routine.",
    ),
    ToolDescriptor(
        key="voice_control",
        label="Voix Eva",
        category="voice",
        policy_level="read_only",
        description="Commandes vocales dans la fenetre Eva avec wake word Ok Eva et reponses vocales.",
    ),
    ToolDescriptor(
        key="daily_launch_brief",
        label="Brief d'ouverture",
        category="automation",
        policy_level="read_only",
        description="Brief automatique a la premiere ouverture de la journee.",
    ),
    ToolDescriptor(
        key="smart_brief",
        label="Smart Brief",
        category="brief",
        policy_level="read_only",
        description="Lit RSS/articles web, score pour Victor, ajoute Gmail/LinkedIn via Gmail si connecte.",
    ),
    ToolDescriptor(
        key="telegram_remote",
        label="Telegram Remote",
        category="messaging",
        policy_level="draft_only",
        description="Pilotage mobile par Telegram avec allowlist locale et auto-execution operator.",
    ),
    ToolDescriptor(
        key="local_command",
        label="Commande locale",
        category="system",
        policy_level="draft_only",
        description="Commande Windows locale auto si non critique; commandes critiques protegees.",
    ),
    ToolDescriptor(
        key="write_file",
        label="Ecriture fichier",
        category="files",
        policy_level="draft_only",
        description="Modification de fichier auto dans les dossiers autorises.",
    ),
)


def list_tools() -> list[dict[str, object]]:
    return [
        {
            "key": tool.key,
            "label": tool.label,
            "category": tool.category,
            "policy_level": tool.policy_level,
            "description": tool.description,
            "enabled": tool.enabled,
        }
        for tool in TOOLS
    ]

from pathlib import Path
from typing import Any, Literal

from app.config import settings
from app.integrations.cli_tools import find_cursor_agent, find_gh, is_gh_authenticated
from app.memory.chat_history_store import CHAT_HISTORY_DB_PATH
from app.memory.memory_store import MEMORY_DB_PATH
from app.memory.obsidian_store import obsidian_status


ReadinessStatus = Literal["ok", "partial", "blocked"]


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _track(
    key: str,
    label: str,
    status: ReadinessStatus,
    done: list[str],
    missing: list[str],
    next_steps: list[str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "done": done,
        "missing": missing,
        "next_steps": next_steps,
        "details": details or {},
    }


def memory_readiness() -> dict[str, Any]:
    obsidian = obsidian_status()
    memory_exists = MEMORY_DB_PATH.exists()
    chat_history_exists = CHAT_HISTORY_DB_PATH.exists()
    obsidian_enabled = bool(obsidian.get("enabled"))
    obsidian_exists = bool(obsidian.get("exists"))

    missing: list[str] = []
    if not memory_exists:
        missing.append("Base memoire SQLite pas encore creee.")
    if not chat_history_exists:
        missing.append("Historique de conversation pas encore cree.")
    if not obsidian_enabled or not obsidian_exists:
        missing.append("Vault Obsidian local inactif ou absent.")

    missing.extend(
        [
            "Consolidation periodique des conversations en souvenirs courts.",
            "Score d'importance et nettoyage des souvenirs doublons.",
            "Recherche semantique locale dans la memoire.",
        ]
    )

    return _track(
        key="memory",
        label="Memoire long terme",
        status="partial" if missing else "ok",
        done=[
            "Profil local injecte dans le prompt Ollama.",
            "Memoires SQLite locales avec protection anti-secrets.",
            "Detection prudente de souvenirs explicites et preferentiels.",
            "Miroir Obsidian local pour lisibilite humaine.",
            "Historique web et Telegram archive localement.",
        ],
        missing=missing,
        next_steps=[
            "Ajouter un job de consolidation quotidienne vers la memoire.",
            "Ajouter une recherche memoire par requete avant chaque reponse importante.",
            "Ajouter une page UI pour corriger/supprimer les souvenirs.",
        ],
        details={
            "memory_db": str(MEMORY_DB_PATH),
            "chat_history_db": str(CHAT_HISTORY_DB_PATH),
            "obsidian": obsidian,
        },
    )


def hands_readiness() -> dict[str, Any]:
    cursor_agent = find_cursor_agent()
    gh = find_gh()
    gh_authenticated = is_gh_authenticated() if gh else False

    missing: list[str] = []
    if not cursor_agent:
        missing.append("cursor-agent CLI absent: autonomie de codage a distance incomplete.")
    if not gh:
        missing.append("GitHub CLI gh absent.")
    if gh and not gh_authenticated:
        missing.append("GitHub CLI installe mais non authentifie avec gh auth login.")
    if not settings.eva_project_factory_auto_execute:
        missing.append("Project Factory auto_execute desactive.")
    if not settings.eva_project_factory_auto_github:
        missing.append("Creation repo GitHub auto desactivee.")
    if not settings.eva_project_factory_auto_push:
        missing.append("Push GitHub auto desactive.")

    status: ReadinessStatus = "ok" if not missing else "partial"
    if not cursor_agent and not gh_authenticated:
        status = "blocked"

    next_steps = [
        "Terminer gh auth login sur le PC.",
        "Ajouter un superviseur de jobs qui relit les logs et relance une correction si besoin.",
    ]
    if not cursor_agent:
        next_steps.insert(1, "Installer WSL puis cursor-agent pour les jobs Cursor sans intervention.")

    return _track(
        key="hands",
        label="Hands / execution locale",
        status=status,
        done=[
            "Creation de workspace projet local.",
            "Generation de README, PROJECT_BRIEF, TASKS et CURSOR_PROMPT.",
            "Generation locale d'une V1 runnable par Eva avant Cursor Agent.",
            "Ouverture Cursor GUI et copie presse-papiers.",
            "Commit Git initial possible.",
            "Creation repo et push prevus via gh.",
        ],
        missing=missing,
        next_steps=next_steps,
        details={
            "cursor_agent": cursor_agent,
            "gh": gh,
            "gh_authenticated": gh_authenticated,
            "auto_execute": settings.eva_project_factory_auto_execute,
            "auto_github": settings.eva_project_factory_auto_github,
            "auto_push": settings.eva_project_factory_auto_push,
        },
    )


def heartbeat_readiness() -> dict[str, Any]:
    missing: list[str] = []
    if not settings.eva_heartbeat_enabled:
        missing.append("Heartbeat desactive dans la configuration.")

    missing.extend(
        [
            "Planification Windows demarrage/session a fiabiliser.",
            "Notifications de fin de job standardisees.",
            "Journal quotidien des jobs autonomes.",
        ]
    )

    return _track(
        key="heartbeat",
        label="Heartbeat / tourne sans toi",
        status="partial",
        done=[
            "Scheduler backend local present.",
            "Brief du matin, tri inbox et journal du soir modelises.",
            "Lancement Windows possible via scripts .bat.",
        ],
        missing=missing,
        next_steps=[
            "Installer Eva au demarrage Windows.",
            "Ajouter un watchdog qui redemarre backend/frontend si un port tombe.",
            "Envoyer un resume Telegram quand un job heartbeat finit.",
        ],
        details={
            "enabled": settings.eva_heartbeat_enabled,
            "poll_seconds": settings.eva_heartbeat_poll_seconds,
        },
    )


def channels_readiness() -> dict[str, Any]:
    telegram_ok = (
        settings.eva_telegram_enabled
        and bool(settings.eva_telegram_bot_token.strip())
        and bool(settings.eva_telegram_allowed_chat_id.strip())
    )
    gmail_enabled = settings.eva_gmail_enabled

    missing: list[str] = []
    if not telegram_ok:
        missing.append("Telegram incomplet: enabled, token ou allowed chat id manquant.")
    if not gmail_enabled:
        missing.append("Gmail desactive ou OAuth pas finalise.")
    missing.append("LinkedIn direct reste en mode brouillon/preparation, pas publication auto.")

    return _track(
        key="channels",
        label="Canaux / iPhone et inbox",
        status="partial" if missing else "ok",
        done=[
            "Telegram bot connectable au PC.",
            "Contexte Telegram court et historique long local.",
            "Gmail OAuth et brouillons de reponse prevus.",
            "LinkedIn assistant en brouillon et lecture prudente.",
        ],
        missing=missing,
        next_steps=[
            "Finaliser Gmail OAuth et tester la lecture inbox/envoyes.",
            "Ajouter des commandes Telegram /jobs et /memory.",
            "Garder publication/envoi sous validation explicite.",
        ],
        details={
            "telegram_enabled": settings.eva_telegram_enabled,
            "telegram_has_token": bool(settings.eva_telegram_bot_token.strip()),
            "telegram_has_allowed_chat_id": bool(settings.eva_telegram_allowed_chat_id.strip()),
            "gmail_enabled": gmail_enabled,
            "linkedin_enabled": settings.eva_linkedin_enabled,
        },
    )


def security_readiness() -> dict[str, Any]:
    missing: list[str] = []
    if not settings.eva_api_token:
        missing.append("Token API absent: routes sensibles bloquees depuis le telephone hors PC local.")
    if settings.cors_origins.strip() == "*":
        missing.append("CORS ouvert: pratique en local, a resserrer si exposition reseau plus large.")

    return _track(
        key="security",
        label="Securite / autonomie encadree",
        status="partial" if missing else "ok",
        done=[
            "Pas d'API OpenAI ni service payant obligatoire.",
            "Secrets et bases locales ignores par Git.",
            "Anti-stockage de mots de passe/tokens dans la memoire.",
            "Politique d'actions: read_only, draft_only, confirmation_required, blocked.",
        ],
        missing=missing,
        next_steps=[
            "Configurer EVA_API_TOKEN si le telephone doit appeler les routes sensibles.",
            "Separer les actions vraiment autonomes des actions critiques.",
            "Ajouter un journal d'audit consultable depuis l'interface.",
        ],
        details={
            "api_token_configured": bool(settings.eva_api_token),
            "cors_origins": settings.parsed_cors_origins,
            "no_openai_required": True,
        },
    )


def autonomy_readiness() -> dict[str, Any]:
    tracks = [
        memory_readiness(),
        hands_readiness(),
        heartbeat_readiness(),
        channels_readiness(),
        security_readiness(),
    ]
    statuses = [track["status"] for track in tracks]
    if "blocked" in statuses:
        status: ReadinessStatus = "blocked"
    elif "partial" in statuses:
        status = "partial"
    else:
        status = "ok"

    return {
        "status": status,
        "summary": (
            "Eva a deja le socle memoire + Telegram + Project Factory. "
            "Le vrai 100% autonome depend surtout de gh auth, cursor-agent/WSL, "
            "consolidation memoire et supervision des jobs."
        ),
        "tracks": tracks,
    }

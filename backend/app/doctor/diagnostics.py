import shutil
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import settings
from app.heartbeat.scheduler import HEARTBEATS_PATH
from app.integrations.linkedin_assistant import LINKEDIN_PATH
from app.integrations.browser import find_browser
from app.integrations.cli_tools import find_cursor_agent, find_gh, is_gh_authenticated
from app.agents.operator_journal import OperatorJournalError, operator_status
from app.memory.embedding_store import EmbeddingStoreError, embedding_status
from app.memory.memory_store import MEMORY_DB_PATH
from app.memory.obsidian_store import obsidian_status
from app.memory.profile_store import PROFILE_PATH, ProfileStoreError, load_profile
from app.security.api_auth import api_security_status
from app.skills.registry import list_skills
from app.tools.rust_indexer import rust_indexer_status


CheckStatus = Literal["ok", "warning", "error"]


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _check(name: str, status: CheckStatus, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details or {},
    }


def _overall_status(checks: list[dict[str, Any]]) -> CheckStatus:
    statuses = {check["status"] for check in checks}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


async def _ollama_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=5.0) as client:
            response = await client.get("/api/tags")
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return [
            _check(
                "ollama_accessible",
                "error",
                f"Ollama indisponible sur {settings.ollama_base_url}.",
                {"error": str(exc)},
            ),
            _check(
                "ollama_model_available",
                "error",
                f"Impossible de verifier le modele {settings.ollama_model}.",
            ),
        ]

    checks.append(
        _check(
            "ollama_accessible",
            "ok",
            f"Ollama repond sur {settings.ollama_base_url}.",
        )
    )

    models = payload.get("models", []) if isinstance(payload, dict) else []
    model_names = [
        str(model.get("name", ""))
        for model in models
        if isinstance(model, dict)
    ]
    configured_model = settings.ollama_model
    model_available = configured_model in model_names or any(
        name.split(":")[0] == configured_model.split(":")[0] for name in model_names
    )

    checks.append(
        _check(
            "ollama_model_available",
            "ok" if model_available else "warning",
            (
                f"Modele {configured_model} disponible."
                if model_available
                else f"Modele {configured_model} non trouve dans Ollama."
            ),
            {"configured_model": configured_model, "installed_models": model_names},
        )
    )

    return checks


def _profile_check() -> dict[str, Any]:
    try:
        profile = load_profile()
    except ProfileStoreError as exc:
        return _check("profile_loaded", "error", str(exc), {"path": str(PROFILE_PATH)})

    identity = profile.get("identity", {}) if isinstance(profile, dict) else {}
    user_name = str(identity.get("user_name", "")).strip() if isinstance(identity, dict) else ""
    return _check(
        "profile_loaded",
        "ok" if user_name else "warning",
        f"Profil Eva charge pour {user_name}." if user_name else "Profil charge sans nom utilisateur.",
        {"path": str(PROFILE_PATH)},
    )


def _gitignore_profile_check() -> dict[str, Any]:
    gitignore_path = PROJECT_ROOT / ".gitignore"
    if not gitignore_path.exists():
        return _check("profile_gitignored", "warning", ".gitignore introuvable.")

    content = gitignore_path.read_text(encoding="utf-8", errors="replace")
    ignored = "data/eva_profile.json" in content or "data/*" in content
    return _check(
        "profile_gitignored",
        "ok" if ignored else "warning",
        (
            "data/eva_profile.json est couvert par .gitignore."
            if ignored
            else "data/eva_profile.json ne semble pas ignore explicitement."
        ),
        {"gitignore": str(gitignore_path)},
    )


def _memory_check() -> dict[str, Any]:
    exists = MEMORY_DB_PATH.exists()
    return _check(
        "memory_sqlite",
        "ok" if exists else "warning",
        "Memoire SQLite presente." if exists else "Memoire SQLite pas encore creee.",
        {"path": str(MEMORY_DB_PATH), "exists": exists},
    )


def _memory_embeddings_check() -> dict[str, Any]:
    if not settings.eva_embeddings_enabled:
        return _check(
            "memory_embeddings",
            "warning",
            "Memoire vectorielle desactivee.",
            {"enabled": False},
        )

    try:
        status = embedding_status()
    except EmbeddingStoreError as exc:
        return _check(
            "memory_embeddings",
            "warning",
            f"Memoire vectorielle non initialisee: {exc}",
        )

    memory_count = int(status.get("memory_count", 0))
    embedding_count = int(status.get("embedding_count", 0))
    if memory_count == 0:
        level: CheckStatus = "ok"
        message = "Memoire vectorielle prete, aucun souvenir a indexer."
    elif embedding_count > 0:
        level = "ok"
        message = f"Memoire vectorielle active: {embedding_count}/{memory_count} souvenirs indexes."
    else:
        level = "warning"
        message = (
            "Memoire vectorielle prete mais pas encore indexee. "
            f"Lance: ollama pull {settings.eva_embedding_model}, puis POST /memory/embeddings/rebuild."
        )

    return _check("memory_embeddings", level, message, status)


def _obsidian_memory_check() -> dict[str, Any]:
    status = obsidian_status()
    enabled = bool(status.get("enabled"))
    exists = bool(status.get("exists"))
    return _check(
        "obsidian_memory",
        "ok" if enabled and exists else "warning",
        (
            "Memoire Obsidian locale active."
            if enabled and exists
            else "Memoire Obsidian locale inactive ou vault absent."
        ),
        status,
    )


def _instructions_check() -> dict[str, Any]:
    expected_paths = [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "start-eva.bat",
        PROJECT_ROOT / "backend" / "requirements.txt",
        PROJECT_ROOT / "frontend" / "package.json",
        PROJECT_ROOT / "frontend" / "vite.config.js",
    ]
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in expected_paths if not path.exists()]
    return _check(
        "frontend_backend_instructions",
        "ok" if not missing else "warning",
        "Instructions et fichiers de lancement presents." if not missing else "Elements de lancement manquants.",
        {"missing": missing},
    )


def _heartbeat_check() -> dict[str, Any]:
    return _check(
        "heartbeat_config",
        "ok" if HEARTBEATS_PATH.exists() else "warning",
        (
            "Configuration heartbeat presente."
            if HEARTBEATS_PATH.exists()
            else "Configuration heartbeat pas encore creee."
        ),
        {"enabled": settings.eva_heartbeat_enabled, "path": str(HEARTBEATS_PATH)},
    )


def _linkedin_check() -> dict[str, Any]:
    return _check(
        "linkedin_assistant",
        "ok" if LINKEDIN_PATH.exists() else "warning",
        (
            "Assistant LinkedIn configure en mode brouillon."
            if LINKEDIN_PATH.exists()
            else "Configuration LinkedIn locale pas encore creee."
        ),
        {
            "enabled": settings.eva_linkedin_enabled,
            "path": str(LINKEDIN_PATH),
            "can_publish": False,
        },
    )


def _skills_check() -> dict[str, Any]:
    skills = list_skills()
    enabled_count = len([skill for skill in skills if skill.get("enabled")])
    return _check(
        "skills_registry",
        "ok" if enabled_count else "warning",
        f"{enabled_count} skills Eva actives.",
        {"enabled_count": enabled_count},
    )


def _telegram_check() -> dict[str, Any]:
    if not settings.eva_telegram_enabled:
        return _check(
            "telegram_bridge",
            "warning",
            "Telegram est desactive.",
            {"enabled": False},
        )

    has_token = bool(settings.eva_telegram_bot_token.strip())
    has_allowed_chat = bool(settings.eva_telegram_allowed_chat_id.strip())
    status: CheckStatus = "ok" if has_token and has_allowed_chat else "warning"
    message = (
        "Telegram est configure pour un chat autorise."
        if status == "ok"
        else "Telegram a un token, mais aucun chat_id autorise n'est encore configure."
        if has_token
        else "Telegram est active, mais le token est absent."
    )
    return _check(
        "telegram_bridge",
        status,
        message,
        {
            "enabled": True,
            "has_token": has_token,
            "has_allowed_chat_id": has_allowed_chat,
        },
    )


def _project_factory_check() -> dict[str, Any]:
    cursor_path = shutil.which("cursor")
    cursor_agent_path = find_cursor_agent()
    gh_path = find_gh()
    gh_authenticated = is_gh_authenticated() if gh_path else False
    auto_github = settings.eva_project_factory_auto_github
    auto_push = settings.eva_project_factory_auto_push
    status: CheckStatus = "ok"
    message = "Project Factory prete pour workspace, presse-papiers et Cursor."
    warnings: list[str] = []

    if settings.eva_project_factory_auto_open_cursor and not cursor_path:
        warnings.append("Cursor CLI est introuvable.")

    if auto_github and not gh_path:
        warnings.append("GitHub auto est active, mais `gh` CLI est introuvable.")

    if auto_github and gh_path and not gh_authenticated:
        warnings.append("GitHub auto est active, mais `gh auth login` n'est pas encore fait.")

    if auto_push and not gh_path:
        warnings.append("Push auto demande un repo GitHub cree via `gh`, mais `gh` CLI est introuvable.")

    if auto_push and gh_path and not gh_authenticated:
        warnings.append("Push auto est active, mais `gh auth login` n'est pas encore fait.")

    if (
        settings.eva_cursor_agent_enabled
        or settings.eva_project_factory_auto_cursor_agent
    ) and not cursor_agent_path:
        warnings.append("cursor-agent CLI est introuvable pour le codage autonome.")

    if warnings:
        status = "warning"
        message = "Project Factory partiellement prete: " + " ".join(warnings)

    return _check(
        "project_factory",
        status,
        message,
        {
            "auto_execute": settings.eva_project_factory_auto_execute,
            "auto_copy_prompt": settings.eva_project_factory_auto_copy_prompt,
            "auto_open_cursor": settings.eva_project_factory_auto_open_cursor,
            "auto_commit": settings.eva_project_factory_auto_commit,
            "auto_github": auto_github,
            "auto_push": auto_push,
            "auto_cursor_agent": settings.eva_project_factory_auto_cursor_agent,
            "agent_repair_once": settings.eva_project_factory_agent_repair_once,
            "agent_auto_commit": settings.eva_project_factory_agent_auto_commit,
            "cursor_cli": cursor_path or "",
            "cursor_agent_cli": cursor_agent_path or "",
            "gh_cli": gh_path or "",
            "gh_authenticated": gh_authenticated,
        },
    )


def _browser_check() -> dict[str, Any]:
    browser = find_browser()
    preference = settings.eva_browser_preference
    return _check(
        "browser_bridge",
        "ok" if browser else "warning",
        (
            f"Navigateur local trouve pour les ouvertures auto: {browser}"
            if browser
            else "Aucun navigateur local trouve pour les ouvertures auto."
        ),
        {
            "preference": preference,
            "browser": browser,
        },
    )


def _api_security_check() -> dict[str, Any]:
    status = api_security_status()
    has_token = bool(status["api_token_configured"])
    cors_is_wildcard = status["cors_origins"] == ["*"]

    if has_token and not cors_is_wildcard:
        level: CheckStatus = "ok"
        message = "Routes sensibles protegees par localhost ou token API."
    elif has_token:
        level = "warning"
        message = "Token API configure, mais CORS accepte encore toutes les origines."
    else:
        level = "warning"
        message = "Aucun token API: les routes sensibles restent limitees au PC local."

    return _check("api_security", level, message, status)


def _operator_journal_check() -> dict[str, Any]:
    try:
        status = operator_status()
    except OperatorJournalError as exc:
        return _check("operator_journal", "warning", str(exc))

    return _check(
        "operator_journal",
        "ok",
        f"Journal operateur actif: {status.get('ticks', 0)} ticks traces.",
        status,
    )


def _rust_indexer_check() -> dict[str, Any]:
    status = rust_indexer_status()
    if status["binary_exists"]:
        return _check(
            "rust_project_indexer",
            "ok",
            "Sidecar Rust compile et disponible pour l'indexation rapide.",
            status,
        )
    if status["cargo_available"]:
        return _check(
            "rust_project_indexer",
            "warning",
            "Source Rust presente, compile le sidecar pour accelerer les scans.",
            status,
        )
    return _check(
        "rust_project_indexer",
        "warning",
        "Rust/cargo absent: Eva utilise le fallback Python pour l'indexation.",
        status,
    )


async def run_doctor() -> dict[str, Any]:
    checks = []
    checks.extend(await _ollama_checks())
    checks.append(_profile_check())
    checks.append(_gitignore_profile_check())
    checks.append(_memory_check())
    checks.append(_memory_embeddings_check())
    checks.append(_obsidian_memory_check())
    checks.append(_instructions_check())
    checks.append(_heartbeat_check())
    checks.append(_linkedin_check())
    checks.append(_skills_check())
    checks.append(_telegram_check())
    checks.append(_project_factory_check())
    checks.append(_browser_check())
    checks.append(_operator_journal_check())
    checks.append(_rust_indexer_check())
    checks.append(_api_security_check())

    status = _overall_status(checks)
    return {
        "status": status,
        "summary": (
            "Eva est prete."
            if status == "ok"
            else "Eva fonctionne, mais certains points demandent attention."
            if status == "warning"
            else "Eva a un probleme bloquant a corriger."
        ),
        "checks": checks,
    }

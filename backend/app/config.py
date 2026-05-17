import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env", override=True)


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "Eva Local Assistant")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    ollama_timeout_seconds: float = _env_float("OLLAMA_TIMEOUT_SECONDS", 90.0)
    ollama_temperature: float = _env_float("OLLAMA_TEMPERATURE", 0.7)
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    eva_api_token: str = os.getenv("EVA_API_TOKEN", "")
    eva_system_actions_enabled: bool = _env_bool("EVA_SYSTEM_ACTIONS_ENABLED", True)
    eva_action_timeout_seconds: float = _env_float("EVA_ACTION_TIMEOUT_SECONDS", 120.0)
    eva_web_search_enabled: bool = _env_bool("EVA_WEB_SEARCH_ENABLED", True)
    eva_gmail_enabled: bool = _env_bool("EVA_GMAIL_ENABLED", False)
    eva_gmail_credentials_path: str = os.getenv(
        "EVA_GMAIL_CREDENTIALS_PATH",
        "data/gmail_credentials.json",
    )
    eva_gmail_token_path: str = os.getenv("EVA_GMAIL_TOKEN_PATH", "data/gmail_token.json")
    eva_gmail_max_sent_examples: int = _env_int("EVA_GMAIL_MAX_SENT_EXAMPLES", 5)
    eva_heartbeat_enabled: bool = _env_bool("EVA_HEARTBEAT_ENABLED", False)
    eva_heartbeat_poll_seconds: int = _env_int("EVA_HEARTBEAT_POLL_SECONDS", 60)
    eva_daily_brief_enabled: bool = _env_bool("EVA_DAILY_BRIEF_ENABLED", True)
    eva_daily_brief_auto_open_tabs: bool = _env_bool("EVA_DAILY_BRIEF_AUTO_OPEN_TABS", False)
    eva_daily_brief_max_tabs: int = _env_int("EVA_DAILY_BRIEF_MAX_TABS", 3)
    eva_linkedin_enabled: bool = _env_bool("EVA_LINKEDIN_ENABLED", True)
    eva_obsidian_memory_enabled: bool = _env_bool("EVA_OBSIDIAN_MEMORY_ENABLED", True)
    eva_obsidian_vault_path: str = os.getenv("EVA_OBSIDIAN_VAULT_PATH", "data/obsidian_vault")
    eva_projects_dir: str = os.getenv("EVA_PROJECTS_DIR", r"C:\Users\victo\Desktop\Cursor")
    eva_project_factory_auto_execute: bool = _env_bool("EVA_PROJECT_FACTORY_AUTO_EXECUTE", False)
    eva_project_factory_auto_copy_prompt: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AUTO_COPY_PROMPT",
        True,
    )
    eva_project_factory_auto_open_cursor: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AUTO_OPEN_CURSOR",
        True,
    )
    eva_project_factory_auto_github: bool = _env_bool("EVA_PROJECT_FACTORY_AUTO_GITHUB", False)
    eva_telegram_enabled: bool = _env_bool("EVA_TELEGRAM_ENABLED", False)
    eva_telegram_bot_token: str = os.getenv("EVA_TELEGRAM_BOT_TOKEN", "")
    eva_telegram_allowed_chat_id: str = os.getenv("EVA_TELEGRAM_ALLOWED_CHAT_ID", "")

    @property
    def parsed_cors_origins(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]

        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


settings = Settings()

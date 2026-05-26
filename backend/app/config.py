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
    ollama_reasoning_model: str = os.getenv(
        "OLLAMA_REASONING_MODEL",
        os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
    )
    ollama_timeout_seconds: float = _env_float("OLLAMA_TIMEOUT_SECONDS", 90.0)
    ollama_reasoning_timeout_seconds: float = _env_float("OLLAMA_REASONING_TIMEOUT_SECONDS", 24.0)
    ollama_temperature: float = _env_float("OLLAMA_TEMPERATURE", 0.7)
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    eva_api_token: str = os.getenv("EVA_API_TOKEN", "")
    eva_autonomy_mode: str = os.getenv("EVA_AUTONOMY_MODE", "operator")
    eva_auto_execute_actions: bool = _env_bool("EVA_AUTO_EXECUTE_ACTIONS", True)
    eva_auto_execute_commands: bool = _env_bool("EVA_AUTO_EXECUTE_COMMANDS", True)
    eva_auto_write_files: bool = _env_bool("EVA_AUTO_WRITE_FILES", True)
    eva_allow_write_any_path: bool = _env_bool("EVA_ALLOW_WRITE_ANY_PATH", False)
    eva_allow_auto_delete: bool = _env_bool("EVA_ALLOW_AUTO_DELETE", False)
    eva_allow_auto_git_push: bool = _env_bool("EVA_ALLOW_AUTO_GIT_PUSH", False)
    eva_allow_auto_external_send: bool = _env_bool("EVA_ALLOW_AUTO_EXTERNAL_SEND", False)
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
    eva_gmail_auto_send_obvious_replies: bool = _env_bool(
        "EVA_GMAIL_AUTO_SEND_OBVIOUS_REPLIES",
        False,
    )
    eva_gmail_auto_reply_query: str = os.getenv(
        "EVA_GMAIL_AUTO_REPLY_QUERY",
        "in:inbox newer_than:7d -category:promotions -category:social",
    )
    eva_gmail_auto_reply_max_per_run: int = _env_int("EVA_GMAIL_AUTO_REPLY_MAX_PER_RUN", 3)
    eva_gmail_auto_reply_min_sent_examples: int = _env_int(
        "EVA_GMAIL_AUTO_REPLY_MIN_SENT_EXAMPLES",
        1,
    )
    eva_gmail_auto_reply_min_confidence: float = _env_float(
        "EVA_GMAIL_AUTO_REPLY_MIN_CONFIDENCE",
        0.9,
    )
    eva_gmail_auto_reply_min_similarity: float = _env_float(
        "EVA_GMAIL_AUTO_REPLY_MIN_SIMILARITY",
        0.34,
    )
    eva_gmail_auto_reply_open_sent_thread: bool = _env_bool(
        "EVA_GMAIL_AUTO_REPLY_OPEN_SENT_THREAD",
        False,
    )
    eva_heartbeat_enabled: bool = _env_bool("EVA_HEARTBEAT_ENABLED", False)
    eva_heartbeat_poll_seconds: int = _env_int("EVA_HEARTBEAT_POLL_SECONDS", 60)
    eva_daily_brief_enabled: bool = _env_bool("EVA_DAILY_BRIEF_ENABLED", True)
    eva_daily_brief_auto_open_tabs: bool = _env_bool("EVA_DAILY_BRIEF_AUTO_OPEN_TABS", False)
    eva_daily_brief_max_tabs: int = _env_int("EVA_DAILY_BRIEF_MAX_TABS", 3)
    eva_browser_preference: str = os.getenv("EVA_BROWSER_PREFERENCE", "brave")
    eva_stitch_enabled: bool = _env_bool("EVA_STITCH_ENABLED", True)
    eva_stitch_url: str = os.getenv("EVA_STITCH_URL", "https://stitch.withgoogle.com")
    eva_stitch_auto_open_browser: bool = _env_bool("EVA_STITCH_AUTO_OPEN_BROWSER", True)
    eva_desktop_automation_enabled: bool = _env_bool("EVA_DESKTOP_AUTOMATION_ENABLED", True)
    eva_spotify_auto_ui_enabled: bool = _env_bool("EVA_SPOTIFY_AUTO_UI_ENABLED", True)
    eva_spotify_ui_delay_seconds: float = _env_float("EVA_SPOTIFY_UI_DELAY_SECONDS", 2.5)
    eva_beeper_enabled: bool = _env_bool("EVA_BEEPER_ENABLED", True)
    eva_beeper_web_url: str = os.getenv("EVA_BEEPER_WEB_URL", "https://chat.beeper.com")
    eva_beeper_open_delay_seconds: float = _env_float("EVA_BEEPER_OPEN_DELAY_SECONDS", 2.5)
    eva_beeper_auto_paste_draft: bool = _env_bool("EVA_BEEPER_AUTO_PASTE_DRAFT", False)
    eva_linkedin_enabled: bool = _env_bool("EVA_LINKEDIN_ENABLED", True)
    eva_linkedin_auto_fill_composer: bool = _env_bool("EVA_LINKEDIN_AUTO_FILL_COMPOSER", True)
    eva_linkedin_auto_fill_delay_seconds: float = _env_float("EVA_LINKEDIN_AUTO_FILL_DELAY_SECONDS", 5.0)
    eva_screen_enabled: bool = _env_bool("EVA_SCREEN_ENABLED", True)
    eva_screen_vision_model: str = os.getenv("EVA_SCREEN_VISION_MODEL", "llava:7b")
    eva_screen_max_captures: int = _env_int("EVA_SCREEN_MAX_CAPTURES", 20)
    eva_screen_watch_enabled: bool = _env_bool("EVA_SCREEN_WATCH_ENABLED", True)
    eva_screen_watch_interval_seconds: int = _env_int("EVA_SCREEN_WATCH_INTERVAL_SECONDS", 60)
    eva_screen_watch_context_max_age_seconds: int = _env_int(
        "EVA_SCREEN_WATCH_CONTEXT_MAX_AGE_SECONDS",
        180,
    )
    eva_visual_action_enabled: bool = _env_bool("EVA_VISUAL_ACTION_ENABLED", True)
    eva_visual_action_min_confidence: float = _env_float("EVA_VISUAL_ACTION_MIN_CONFIDENCE", 0.62)
    eva_obsidian_memory_enabled: bool = _env_bool("EVA_OBSIDIAN_MEMORY_ENABLED", True)
    eva_obsidian_vault_path: str = os.getenv("EVA_OBSIDIAN_VAULT_PATH", "data/obsidian_vault")
    eva_embeddings_enabled: bool = _env_bool("EVA_EMBEDDINGS_ENABLED", True)
    eva_embedding_model: str = os.getenv("EVA_EMBEDDING_MODEL", "nomic-embed-text")
    eva_embedding_timeout_seconds: float = _env_float("EVA_EMBEDDING_TIMEOUT_SECONDS", 20.0)
    eva_memory_vector_candidates: int = _env_int("EVA_MEMORY_VECTOR_CANDIDATES", 120)
    eva_cursor_auto_copy_prompt: bool = _env_bool("EVA_CURSOR_AUTO_COPY_PROMPT", True)
    eva_cursor_auto_open_project: bool = _env_bool("EVA_CURSOR_AUTO_OPEN_PROJECT", True)
    eva_cursor_write_prompt_file: bool = _env_bool("EVA_CURSOR_WRITE_PROMPT_FILE", True)
    eva_cursor_agent_enabled: bool = _env_bool("EVA_CURSOR_AGENT_ENABLED", True)
    eva_cursor_agent_background: bool = _env_bool("EVA_CURSOR_AGENT_BACKGROUND", True)
    eva_telegram_context_messages: int = _env_int("EVA_TELEGRAM_CONTEXT_MESSAGES", 16)
    eva_reasoning_enabled: bool = _env_bool("EVA_REASONING_ENABLED", True)
    eva_reasoning_min_confidence: float = _env_float("EVA_REASONING_MIN_CONFIDENCE", 0.55)
    eva_reasoning_max_attempts: int = _env_int("EVA_REASONING_MAX_ATTEMPTS", 4)
    eva_reasoning_web_fallback_enabled: bool = _env_bool("EVA_REASONING_WEB_FALLBACK_ENABLED", True)
    eva_reasoning_force_structured_trace: bool = _env_bool(
        "EVA_REASONING_FORCE_STRUCTURED_TRACE",
        True,
    )
    eva_problem_solver_enabled: bool = _env_bool("EVA_PROBLEM_SOLVER_ENABLED", True)
    eva_problem_solver_max_cycles: int = _env_int("EVA_PROBLEM_SOLVER_MAX_CYCLES", 6)
    eva_projects_dir: str = os.getenv("EVA_PROJECTS_DIR", r"C:\Users\victo\Desktop\Cursor")
    eva_project_factory_auto_execute: bool = _env_bool("EVA_PROJECT_FACTORY_AUTO_EXECUTE", True)
    eva_project_factory_auto_commit: bool = _env_bool("EVA_PROJECT_FACTORY_AUTO_COMMIT", True)
    eva_project_factory_auto_copy_prompt: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AUTO_COPY_PROMPT",
        True,
    )
    eva_project_factory_auto_open_cursor: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AUTO_OPEN_CURSOR",
        True,
    )
    eva_project_factory_auto_github: bool = _env_bool("EVA_PROJECT_FACTORY_AUTO_GITHUB", True)
    eva_project_factory_auto_push: bool = _env_bool("EVA_PROJECT_FACTORY_AUTO_PUSH", True)
    eva_project_factory_auto_cursor_agent: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AUTO_CURSOR_AGENT",
        True,
    )
    eva_project_factory_agent_repair_once: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AGENT_REPAIR_ONCE",
        True,
    )
    eva_project_factory_agent_auto_commit: bool = _env_bool(
        "EVA_PROJECT_FACTORY_AGENT_AUTO_COMMIT",
        True,
    )
    eva_project_factory_agent_timeout_seconds: float = _env_float(
        "EVA_PROJECT_FACTORY_AGENT_TIMEOUT_SECONDS",
        3600.0,
    )
    eva_self_improve_enabled: bool = _env_bool("EVA_SELF_IMPROVE_ENABLED", True)
    eva_self_improve_project_name: str = os.getenv("EVA_SELF_IMPROVE_PROJECT_NAME", "Eva")
    eva_self_improve_auto_cursor_agent: bool = _env_bool(
        "EVA_SELF_IMPROVE_AUTO_CURSOR_AGENT",
        False,
    )
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

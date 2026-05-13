import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return float(raw_value)
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
    eva_system_actions_enabled: bool = _env_bool("EVA_SYSTEM_ACTIONS_ENABLED", True)
    eva_action_timeout_seconds: float = _env_float("EVA_ACTION_TIMEOUT_SECONDS", 120.0)
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

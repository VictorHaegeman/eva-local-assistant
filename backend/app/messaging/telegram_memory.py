import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.memory.chat_history_store import ChatHistoryError, get_recent_chat_messages


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
TELEGRAM_CONVERSATIONS_PATH = DATA_DIR / "eva_telegram_conversations.json"


def _load_payload() -> dict[str, Any]:
    try:
        payload = json.loads(TELEGRAM_CONVERSATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"conversations": {}}

    if not isinstance(payload, dict):
        return {"conversations": {}}
    if not isinstance(payload.get("conversations"), dict):
        payload["conversations"] = {}
    return payload


def _save_payload(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TELEGRAM_CONVERSATIONS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _conversation_key(chat_id: int) -> str:
    return str(chat_id)


def load_telegram_context(chat_id: int) -> list[dict[str, str]]:
    payload = _load_payload()
    conversation = payload["conversations"].get(_conversation_key(chat_id), [])
    if not isinstance(conversation, list):
        return []

    limit = max(0, min(settings.eva_telegram_context_messages, 40))
    messages: list[dict[str, str]] = []
    for item in conversation[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:6000]})
    if len(messages) >= limit:
        return messages

    try:
        archived_messages = get_recent_chat_messages(f"telegram-{chat_id}", limit=limit)
    except ChatHistoryError:
        return messages

    archived_context = [
        {"role": message.role, "content": message.content[:6000]}
        for message in archived_messages
        if message.role in {"user", "assistant"} and message.content.strip()
    ]

    if not messages:
        return archived_context[-limit:]

    seen = {(message["role"], message["content"]) for message in messages}
    merged = [
        message
        for message in archived_context
        if (message["role"], message["content"]) not in seen
    ]
    merged.extend(messages)
    return merged[-limit:]


def append_telegram_exchange(chat_id: int, user_text: str, assistant_text: str) -> None:
    payload = _load_payload()
    conversations = payload["conversations"]
    key = _conversation_key(chat_id)
    conversation = conversations.get(key, [])
    if not isinstance(conversation, list):
        conversation = []

    now = datetime.now(UTC).isoformat()
    conversation.extend(
        [
            {
                "role": "user",
                "content": user_text[:6000],
                "created_at": now,
            },
            {
                "role": "assistant",
                "content": assistant_text[:6000],
                "created_at": now,
            },
        ]
    )

    max_items = max(4, min(settings.eva_telegram_context_messages * 2, 80))
    conversations[key] = conversation[-max_items:]
    _save_payload(payload)


def clear_telegram_context(chat_id: int) -> None:
    payload = _load_payload()
    payload["conversations"][_conversation_key(chat_id)] = []
    _save_payload(payload)

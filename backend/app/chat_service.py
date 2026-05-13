from typing import Any

from app.actions.action_detector import create_pending_action_from_message
from app.actions.action_store import ActionStoreError, action_to_dict
from app.files.file_context import detect_file_context
from app.files.local_files import LocalFileError
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.memory_store import (
    MemoryStoreError,
    add_memory,
    detect_auto_memory_candidate,
    detect_explicit_memory_request,
    memory_to_dict,
)


class ChatServiceError(Exception):
    """Raised when Eva cannot process a chat message."""


async def process_chat_messages(
    safe_messages: list[dict[str, str]],
) -> dict[str, Any]:
    if not safe_messages or safe_messages[-1]["role"] != "user":
        raise ChatServiceError("La conversation doit se terminer par un message utilisateur.")

    saved_memory = None
    latest_user_message = safe_messages[-1]["content"]
    extra_context = None

    try:
        pending_action = create_pending_action_from_message(latest_user_message)
        if pending_action:
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        f"J'ai prepare l'action #{pending_action.id}: {pending_action.title}.\n"
                        "Elle est en attente de validation. Depuis Telegram: /approve "
                        f"{pending_action.id}. Depuis l'API: POST /actions/{pending_action.id}/approve."
                    ),
                },
                "saved_memory": None,
                "pending_action": action_to_dict(pending_action),
            }
    except ActionStoreError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        memory_content = detect_explicit_memory_request(latest_user_message)
        if memory_content:
            saved_memory = memory_to_dict(add_memory(memory_content, source="explicit"))
        else:
            memory_candidate = detect_auto_memory_candidate(latest_user_message)
            if memory_candidate:
                saved_memory = memory_to_dict(
                    add_memory(
                        memory_candidate.content,
                        category=memory_candidate.category,
                        source="auto",
                        confidence=memory_candidate.confidence,
                    )
                )
    except MemoryStoreError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        file_context = detect_file_context(latest_user_message)
        if file_context:
            extra_context = (
                f"Fichier local lu en lecture seule: {file_context['root']}/{file_context['path']}\n\n"
                f"{file_context['content']}"
            )
    except LocalFileError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        answer = await ask_ollama(safe_messages, extra_context=extra_context)
    except OllamaClientError as exc:
        raise ChatServiceError(str(exc)) from exc

    return {
        "message": {"role": "assistant", "content": answer},
        "saved_memory": saved_memory,
        "pending_action": None,
    }

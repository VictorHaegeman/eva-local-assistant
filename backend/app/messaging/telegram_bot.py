import asyncio
import json
from pathlib import Path
from typing import Any

import httpx

from app.actions.action_store import (
    ActionStoreError,
    action_to_dict,
    list_actions,
    update_action_status,
)
from app.actions.executor import ActionExecutionError, execute_action
from app.chat_service import ChatServiceError, process_chat_messages
from app.config import settings
from app.messaging.telegram_memory import (
    append_telegram_exchange,
    clear_telegram_context,
    load_telegram_context,
)
from app.memory.chat_history_store import ChatHistoryError, append_chat_exchange
from app.project_factory.automation import (
    auto_execute_project_factory_actions,
    format_project_factory_results,
    project_factory_auto_status,
)
from app.project_factory.planner import ProjectFactoryError, create_project_factory_actions
from app.projects.project_chat import build_cursor_work_session_response
from app.projects.project_store import ProjectStoreError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
TELEGRAM_STATE_PATH = DATA_DIR / "eva_telegram_state.json"

MAX_TELEGRAM_MESSAGE = 3500


class TelegramBotError(Exception):
    """Raised when the Telegram bridge cannot run."""


def telegram_config_status() -> dict[str, object]:
    return {
        "enabled": settings.eva_telegram_enabled,
        "has_token": bool(settings.eva_telegram_bot_token),
        "has_allowed_chat_id": bool(settings.eva_telegram_allowed_chat_id),
    }


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.eva_telegram_bot_token}/{method}"


def _load_offset() -> int:
    try:
        payload = json.loads(TELEGRAM_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0

    return int(payload.get("offset", 0))


def _save_offset(offset: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    TELEGRAM_STATE_PATH.write_text(
        json.dumps({"offset": offset}, indent=2),
        encoding="utf-8",
    )


def _is_allowed_chat(chat_id: int) -> bool:
    allowed_chat_id = settings.eva_telegram_allowed_chat_id.strip()
    return bool(allowed_chat_id) and str(chat_id) == allowed_chat_id


async def _send_message(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    chunks = [
        text[index : index + MAX_TELEGRAM_MESSAGE]
        for index in range(0, len(text), MAX_TELEGRAM_MESSAGE)
    ] or [""]

    for chunk in chunks:
        await client.post(
            _api_url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": chunk,
            },
        )


def _format_pending_actions() -> str:
    actions = list_actions(status="pending", limit=20)
    if not actions:
        return "Aucune action en attente."

    lines = ["Actions en attente:"]
    for action in actions:
        lines.append(f"#{action.id} [{action.action_type}] {action.title}")
        if action.description:
            lines.append(f"  {action.description}")

    lines.append("")
    lines.append("Valider: /approve ID")
    lines.append("Refuser: /reject ID")
    return "\n".join(lines)


async def _handle_command(client: httpx.AsyncClient, chat_id: int, text: str) -> bool:
    command_parts = text.strip().split(maxsplit=1)
    command = command_parts[0].lower()
    argument = command_parts[1].strip() if len(command_parts) > 1 else ""

    if command in {"/start", "/help"}:
        await _send_message(
            client,
            chat_id,
            (
                "Eva est connectee.\n\n"
                "Commandes:\n"
                "/project IDEE - preparer workspace, prompt Cursor et repo GitHub\n"
                "/idea IDEE - alias de /project\n"
                "/cursor PROJET + TACHE - ouvrir Cursor et copier le prompt\n"
                "/codex PROJET + TACHE - alias de /cursor\n"
                "/reset - oublier le fil Telegram courant\n"
                "/pending - voir les actions en attente\n"
                "/approve ID - valider et executer une action\n"
                "/reject ID - refuser une action\n"
                "/status - verifier la connexion\n\n"
                "Tout message normal est envoye au chat local Eva."
            ),
        )
        return True

    if command == "/status":
        await _send_message(client, chat_id, "Eva Telegram est active sur ce PC.")
        return True

    if command == "/reset":
        clear_telegram_context(chat_id)
        await _send_message(client, chat_id, "Contexte Telegram remis a zero.")
        return True

    if command in {"/project", "/idea"}:
        if not argument:
            await _send_message(
                client,
                chat_id,
                "Usage: /project idee du projet a preparer",
            )
            return True

        try:
            bundle = create_project_factory_actions(argument)
            plan = bundle["plan"]
            actions = bundle["actions"]
            auto_status = project_factory_auto_status()
            if auto_status["auto_execute"]:
                results = auto_execute_project_factory_actions(actions)
                await _send_message(client, chat_id, format_project_factory_results(plan, results))
                return True

            lines = [
                f"Project Factory pret: {plan['project_name']}",
                f"Dossier cible: {plan['workspace_path']}",
                f"Repo propose: {plan['repo_name']}",
                "",
                "Actions creees en attente:",
            ]
            for action in actions:
                lines.append(f"#{action.id} [{action.action_type}] {action.title}")
            lines.extend(
                [
                    "",
                    "Valide chaque etape avec /approve ID.",
                    "Workspace, Cursor, presse-papiers et GitHub restent derriere validation.",
                ]
            )
            await _send_message(client, chat_id, "\n".join(lines))
        except (ProjectFactoryError, ActionStoreError) as exc:
            await _send_message(client, chat_id, f"Erreur Project Factory: {exc}")
        return True

    if command in {"/cursor", "/codex", "/work"}:
        if not argument:
            await _send_message(
                client,
                chat_id,
                "Usage: /cursor nom du projet + ce que Cursor/Codex doit faire",
            )
            return True

        try:
            await _send_message(client, chat_id, build_cursor_work_session_response(argument))
        except ProjectStoreError as exc:
            await _send_message(client, chat_id, f"Erreur Cursor bridge: {exc}")
        return True

    if command == "/pending":
        try:
            await _send_message(client, chat_id, _format_pending_actions())
        except ActionStoreError as exc:
            await _send_message(client, chat_id, str(exc))
        return True

    if command == "/approve":
        try:
            action_id = int(argument)
            update_action_status(action_id, "approved")
            result = execute_action(action_id)
            action = result["action"]
            if isinstance(action, dict):
                await _send_message(
                    client,
                    chat_id,
                    (
                        f"Action #{action_id} executee: {result['executed']}\n\n"
                        f"Resultat:\n{action.get('result', '')}"
                    ),
                )
            else:
                await _send_message(client, chat_id, f"Action #{action_id} traitee.")
        except (ValueError, ActionStoreError, ActionExecutionError) as exc:
            await _send_message(client, chat_id, f"Erreur approval: {exc}")
        return True

    if command == "/reject":
        try:
            action_id = int(argument)
            action = update_action_status(
                action_id,
                "rejected",
                "Action rejetee depuis Telegram.",
            )
            await _send_message(client, chat_id, f"Action #{action.id} rejetee.")
        except (ValueError, ActionStoreError) as exc:
            await _send_message(client, chat_id, f"Erreur reject: {exc}")
        return True

    return False


async def _handle_text_message(client: httpx.AsyncClient, chat_id: int, text: str) -> None:
    if text.startswith("/"):
        handled = await _handle_command(client, chat_id, text)
        if handled:
            return

    try:
        context = load_telegram_context(chat_id)
        result = await process_chat_messages(
            [*context, {"role": "user", "content": text}],
            trusted_actions=True,
        )
    except ChatServiceError as exc:
        await _send_message(client, chat_id, f"Eva ne peut pas repondre: {exc}")
        return

    pending_action = result.get("pending_action")
    suffix = ""
    if isinstance(pending_action, dict):
        suffix = f"\n\nAction en attente: #{pending_action.get('id')} - /approve {pending_action.get('id')}"

    assistant_text = str(result["message"]["content"])
    append_telegram_exchange(chat_id, text, assistant_text)
    try:
        append_chat_exchange(
            f"telegram-{chat_id}",
            text,
            assistant_text,
            channel="telegram",
        )
    except ChatHistoryError:
        pass
    await _send_message(client, chat_id, f"{assistant_text}{suffix}")


async def _handle_update(client: httpx.AsyncClient, update: dict[str, Any]) -> None:
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return

    chat_id = int(chat.get("id", 0))
    text = str(message.get("text", "")).strip()

    if not text:
        await _send_message(
            client,
            chat_id,
            "Pour l'instant Eva Telegram accepte seulement les messages texte.",
        )
        return

    if not settings.eva_telegram_allowed_chat_id:
        await _send_message(
            client,
            chat_id,
            (
                f"Chat ID detecte: {chat_id}\n"
                "Ajoute cette valeur dans EVA_TELEGRAM_ALLOWED_CHAT_ID puis redemarre Eva."
            ),
        )
        return

    if not _is_allowed_chat(chat_id):
        return

    await _handle_text_message(client, chat_id, text)


async def telegram_polling_loop() -> None:
    if not settings.eva_telegram_enabled:
        return

    if not settings.eva_telegram_bot_token:
        return

    offset = _load_offset()

    async with httpx.AsyncClient(timeout=35.0) as client:
        while True:
            try:
                response = await client.get(
                    _api_url("getUpdates"),
                    params={
                        "timeout": 25,
                        "offset": offset,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                updates = payload.get("result", [])

                for update in updates:
                    update_id = int(update.get("update_id", 0))
                    offset = max(offset, update_id + 1)
                    await _handle_update(client, update)

                _save_offset(offset)
            except Exception:
                await asyncio.sleep(5)


def start_telegram_background_task() -> asyncio.Task[None] | None:
    if not settings.eva_telegram_enabled or not settings.eva_telegram_bot_token:
        return None

    return asyncio.create_task(telegram_polling_loop())

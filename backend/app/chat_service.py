from typing import Any

from app.actions.action_detector import create_pending_action_from_message
from app.actions.action_store import ActionStoreError, action_to_dict, list_actions
from app.briefs.smart_brief import SmartBriefError, generate_smart_brief_payload
from app.config import settings
from app.files.file_context import detect_file_context
from app.files.local_files import LocalFileError, roots_to_dicts
from app.heartbeat.scheduler import HeartbeatError, heartbeat_status
from app.agents.intent_router import classify_user_intent, format_intent_context
from app.integrations.gmail_chat import (
    build_gmail_chat_response,
    wants_gmail_list,
    wants_gmail_reply_draft,
)
from app.integrations.gmail_client import GmailIntegrationError
from app.integrations.google_setup_chat import (
    build_calendar_events_response,
    build_google_setup_response,
    wants_calendar_events,
    wants_google_account_setup,
)
from app.integrations.linkedin_assistant import (
    LinkedInAssistantError,
    build_linkedin_chat_response,
    wants_linkedin_browser_post,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.memory_store import (
    MemoryStoreError,
    add_memory,
    detect_auto_memory_candidate,
    detect_explicit_memory_request,
    memory_to_dict,
)
from app.memory.obsidian_store import ObsidianMemoryError, mirror_memory_to_obsidian
from app.memory.obsidian_store import obsidian_status
from app.projects.project_chat import (
    ProjectStoreError,
    build_chat_cursor_prompt_response,
    build_cursor_work_session_response,
    build_project_context_for_chat,
    detect_cursor_prompt_request,
)
from app.projects.project_store import load_projects
from app.project_factory.automation import (
    auto_execute_project_factory_actions,
    format_project_factory_results,
    project_factory_auto_status,
)
from app.project_factory.planner import ProjectFactoryError, create_project_factory_actions
from app.screen.screen_reader import ScreenReaderError, analyze_screen
from app.skills.registry import list_skills
from app.terminal.terminal_doctor import (
    analyze_terminal_error,
    format_terminal_diagnosis,
    launch_terminal_fix,
    looks_like_terminal_error,
)
from app.tools.registry import list_tools
from app.web.web_search import WebSearchError, detect_web_search_query, format_web_results, search_web


class ChatServiceError(Exception):
    """Raised when Eva cannot process a chat message."""


PROJECT_CONTEXT_MARKERS = (
    "projet",
    "repo",
    "code",
    "cursor",
    "codex",
    "bug",
    "readme",
    "branche",
    "pr ",
)

PROJECT_FACTORY_MARKERS = (
    "nouveau projet",
    "nouvelle idee projet",
    "nouvelle idée projet",
    "cree un projet",
    "crée un projet",
    "creer un projet",
    "créer un projet",
    "project factory",
)


def _should_attach_project_context(message: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in PROJECT_CONTEXT_MARKERS)


def _should_create_project_factory_plan(message: str) -> bool:
    normalized = message.lower()
    return any(marker in normalized for marker in PROJECT_FACTORY_MARKERS)


def _mirror_memory(memory: object) -> None:
    try:
        mirror_memory_to_obsidian(memory)
    except ObsidianMemoryError:
        pass


def _format_quick_status(message: str) -> str | None:
    normalized = message.lower()

    if "skills" in normalized or "competences" in normalized:
        skills = list_skills()
        lines = ["Skills Eva actives:"]
        for skill in skills:
            lines.append(f"- {skill['label']} [{skill['policy_level']}]: {skill['description']}")
        return "\n".join(lines)

    if "obsidian" in normalized:
        status = obsidian_status()
        return (
            f"Memoire Obsidian: {'activee' if status['enabled'] else 'desactivee'}\n"
            f"Vault: {status['path']}\n"
            f"Fichiers Markdown: {status['markdown_files']}\n"
            "Le vault est local et ignore par Git."
        )

    if "tools" in normalized or "capacites" in normalized:
        tools = list_tools()
        lines = ["Tools Eva actifs:"]
        for tool in tools:
            lines.append(f"- {tool['label']} [{tool['policy_level']}]: {tool['description']}")
        return "\n".join(lines)

    if "actions" in normalized and "attente" in normalized:
        pending = list_actions(status="pending", limit=20)
        if not pending:
            return "Aucune action locale en attente."
        lines = ["Actions locales en attente:"]
        for action in pending:
            lines.append(f"- #{action.id} [{action.action_type}] {action.title}")
        return "\n".join(lines)

    if "ollama" in normalized and ("statut" in normalized or "modele" in normalized):
        return (
            f"Ollama configure: {settings.ollama_base_url}\n"
            f"Modele configure: {settings.ollama_model}\n"
            "Pour un diagnostic complet, consulte le panneau Doctor."
        )

    if "heartbeat" in normalized or "heartbeats" in normalized:
        status = heartbeat_status()
        lines = [
            f"Heartbeats actives: {status['enabled']}",
            f"Poll: {status['poll_seconds']} secondes",
        ]
        for job in status["jobs"]:
            lines.append(
                f"- {job.get('label', job.get('key'))}: "
                f"{'actif' if job.get('enabled') else 'inactif'} a {job.get('time', '--:--')}"
            )
        return "\n".join(lines)

    if "brief" in normalized and any(marker in normalized for marker in ("matin", "smart", "veille", "aujourd")):
        return "__GENERATE_SMART_BRIEF__"

    if "dossiers autorises" in normalized or "fichiers" in normalized and "autorises" in normalized:
        roots = roots_to_dicts()
        lines = ["Dossiers autorises:"]
        for root in roots:
            lines.append(f"- {root['name']}: {root['path']}")
        return "\n".join(lines)

    if "projets locaux" in normalized or ("projets" in normalized and "connais" in normalized):
        projects = load_projects()
        lines = ["Projets locaux connus:"]
        for project in projects:
            lines.append(f"- {project['name']}: {project['path']}")
        return "\n".join(lines)

    return None


def _quick_status_requires_trusted_access(message: str) -> bool:
    normalized = message.lower()
    trusted_markers = (
        "actions",
        "obsidian",
        "brief",
        "dossiers autorises",
        "fichiers autorises",
        "projets locaux",
        "projets",
        "heartbeat",
        "heartbeats",
    )
    return any(marker in normalized for marker in trusted_markers)


async def process_chat_messages(
    safe_messages: list[dict[str, str]],
    mode: str = "chat",
    trusted_actions: bool = False,
) -> dict[str, Any]:
    if not safe_messages or safe_messages[-1]["role"] != "user":
        raise ChatServiceError("La conversation doit se terminer par un message utilisateur.")

    saved_memory = None
    latest_user_message = safe_messages[-1]["content"]
    user_intent = classify_user_intent(latest_user_message)
    intent_context = format_intent_context(user_intent)
    context_blocks: list[str] = []

    try:
        if user_intent.name == "screen_read":
            if not trusted_actions:
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "Lire l'ecran expose des donnees privees. Je peux le faire depuis "
                            "le PC local ou Telegram autorise, pas depuis une session non fiable."
                        ),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }
            screen_result = await analyze_screen(
                instruction=latest_user_message,
                auto_fix=True,
            )
            launched = screen_result.get("launched")
            launched_line = (
                f"\n\nAction locale lancee: {launched.get('message')}"
                if isinstance(launched, dict)
                else ""
            )
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        f"{intent_context}\n\n"
                        f"Analyse ecran via {screen_result['vision_model']}:\n"
                        f"{screen_result['analysis']}"
                        f"{launched_line}"
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if user_intent.name == "terminal_error" or looks_like_terminal_error(latest_user_message):
            diagnosis = analyze_terminal_error(latest_user_message)
            launched = None
            if trusted_actions and diagnosis.fix and diagnosis.fix.safe_to_launch:
                launched = launch_terminal_fix(diagnosis.fix.key)
            return {
                "message": {
                    "role": "assistant",
                        "content": f"{intent_context}\n\n{format_terminal_diagnosis(diagnosis, launched=launched)}",
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if user_intent.name == "google_oauth_setup":
            return {
                "message": {
                    "role": "assistant",
                    "content": build_google_setup_response(
                        trusted_actions=trusted_actions,
                        intent_context=intent_context,
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if user_intent.name == "project_factory" or _should_create_project_factory_plan(latest_user_message):
            if not trusted_actions:
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "Cette demande implique des actions locales sur ton PC. "
                            "Je peux le faire depuis le PC local ou depuis ton Telegram autorise, "
                            "mais pas depuis une session non fiable du reseau."
                        ),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }

            bundle = create_project_factory_actions(latest_user_message)
            plan = bundle["plan"]
            actions = bundle["actions"]
            auto_status = project_factory_auto_status()
            if auto_status["auto_execute"]:
                results = auto_execute_project_factory_actions(actions)
                content = format_project_factory_results(plan, results)
                return {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }

            first_action = actions[0]
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        "J'ai prepare un plan Project Factory local.\n\n"
                        f"Projet: {plan['project_name']}\n"
                        f"Dossier cible: {plan['workspace_path']}\n"
                        f"Repo GitHub propose: {plan['repo_name']}\n"
                        f"Stack: {plan['stack']['frontend']} / {plan['stack']['backend']}\n\n"
                        "Actions en attente:\n"
                        + "\n".join(f"- #{action.id} [{action.action_type}] {action.title}" for action in actions)
                        + "\n\nActive EVA_PROJECT_FACTORY_AUTO_EXECUTE=true pour lancer automatiquement ce flux."
                    ),
                },
                "saved_memory": None,
                "pending_action": action_to_dict(first_action),
            }

        pending_action = create_pending_action_from_message(latest_user_message)
        if pending_action:
            if not trusted_actions:
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "J'ai detecte une action locale, mais je ne peux pas la creer depuis "
                            "une session non fiable. Refais la demande depuis le PC local ou Telegram autorise."
                        ),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }

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
    except (ActionStoreError, ProjectFactoryError, ScreenReaderError) as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if not trusted_actions and _quick_status_requires_trusted_access(latest_user_message):
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Cette demande consulte l'etat local d'Eva. Je peux le faire depuis "
                        "le PC local ou Telegram autorise, mais pas depuis une session non fiable."
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        quick_status = _format_quick_status(latest_user_message)
        if quick_status:
            if quick_status == "__GENERATE_SMART_BRIEF__":
                payload = await generate_smart_brief_payload()
                stats = payload.get("stats", {})
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"{payload['brief'].content}\n\n"
                            f"Stats: {stats.get('rss_items', 0)} items RSS, "
                            f"{stats.get('articles_read', 0)} articles lus, "
                            f"{stats.get('gmail_messages', 0)} mails, "
                            f"{stats.get('linkedin_notifications', 0)} signaux LinkedIn via Gmail."
                        ),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }
            return {
                "message": {
                    "role": "assistant",
                    "content": quick_status,
                },
                "saved_memory": None,
                "pending_action": None,
            }
    except (ActionStoreError, HeartbeatError, LocalFileError, ProjectStoreError, SmartBriefError) as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if user_intent.name == "calendar_read" or wants_calendar_events(latest_user_message):
            if not trusted_actions:
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "Google Calendar contient des donnees privees. Je peux le lire depuis "
                            "le PC local ou Telegram autorise, mais pas depuis une session non fiable."
                        ),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }
            return {
                "message": {
                    "role": "assistant",
                    "content": build_calendar_events_response(days=7),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if wants_google_account_setup(latest_user_message):
            return {
                "message": {
                    "role": "assistant",
                    "content": build_google_setup_response(
                        trusted_actions=trusted_actions,
                        intent_context=intent_context,
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if not trusted_actions and (
            user_intent.name in {"gmail_read", "gmail_reply_draft"}
            or wants_gmail_list(latest_user_message)
            or wants_gmail_reply_draft(latest_user_message)
        ):
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Gmail contient des donnees privees. Je peux le lire depuis le PC local "
                        "ou Telegram autorise, mais pas depuis une session non fiable."
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        gmail_response = await build_gmail_chat_response(latest_user_message)
        if gmail_response:
            return {
                "message": {
                    "role": "assistant",
                    "content": gmail_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }
    except GmailIntegrationError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if not trusted_actions and wants_linkedin_browser_post(latest_user_message):
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Ouvrir LinkedIn et preparer le navigateur est une action locale. "
                        "Je peux le faire depuis le PC local ou Telegram autorise."
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        linkedin_response = await build_linkedin_chat_response(latest_user_message)
        if linkedin_response:
            return {
                "message": {
                    "role": "assistant",
                    "content": linkedin_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }
    except LinkedInAssistantError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if detect_cursor_prompt_request(latest_user_message):
            if trusted_actions:
                return {
                    "message": {
                        "role": "assistant",
                        "content": build_cursor_work_session_response(latest_user_message),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }

            return {
                "message": {
                    "role": "assistant",
                    "content": build_chat_cursor_prompt_response(latest_user_message),
                },
                "saved_memory": None,
                "pending_action": None,
            }
    except ProjectStoreError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        memory_content = detect_explicit_memory_request(latest_user_message) if trusted_actions else None
        if memory_content:
            memory = add_memory(memory_content, source="explicit")
            _mirror_memory(memory)
            saved_memory = memory_to_dict(memory)
        elif trusted_actions:
            memory_candidate = detect_auto_memory_candidate(latest_user_message)
            if memory_candidate:
                memory = add_memory(
                    memory_candidate.content,
                    category=memory_candidate.category,
                    source="auto",
                    confidence=memory_candidate.confidence,
                )
                _mirror_memory(memory)
                saved_memory = memory_to_dict(memory)
    except MemoryStoreError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        file_context = detect_file_context(latest_user_message) if trusted_actions else None
        if file_context:
            context_blocks.append(
                f"Fichier local lu en lecture seule: {file_context['root']}/{file_context['path']}\n\n"
                f"{file_context['content']}"
            )
    except LocalFileError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        web_query = detect_web_search_query(latest_user_message)
        if web_query:
            web_results = await search_web(web_query)
            context_blocks.append(format_web_results(web_query, web_results))
    except WebSearchError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if trusted_actions and _should_attach_project_context(latest_user_message):
            project_context = build_project_context_for_chat(latest_user_message)
            if project_context:
                context_blocks.append(project_context)
    except ProjectStoreError as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        extra_context = "\n\n---\n\n".join(context_blocks) if context_blocks else None
        answer = await ask_ollama(safe_messages, extra_context=extra_context, mode=mode)
    except OllamaClientError as exc:
        raise ChatServiceError(str(exc)) from exc

    return {
        "message": {"role": "assistant", "content": answer},
        "saved_memory": saved_memory,
        "pending_action": None,
    }

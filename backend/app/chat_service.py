import re
import unicodedata
from typing import Any

from app.actions.action_detector import create_pending_action_from_message
from app.actions.action_store import ActionStoreError, action_to_dict, list_actions
from app.actions.executor import ActionExecutionError, execute_action
from app.briefs.smart_brief import SmartBriefError, generate_smart_brief_payload
from app.cognition.cognitive_loop import build_reasoning_trace, run_cognitive_loop
from app.cognition.context import attach_cognitive_context, build_cognitive_context, format_cognitive_context
from app.cognition.ml_adaptation import build_ml_adaptation_context
from app.cognition.problem_solver import (
    build_direct_problem_solver_response,
    build_passive_refusal_recovery,
    looks_like_passive_refusal,
)
from app.cognition.structured_interpreter import refine_understanding_with_ollama
from app.config import settings
from app.files.file_context import detect_file_context
from app.files.local_files import LocalFileError, roots_to_dicts
from app.heartbeat.scheduler import HeartbeatError, heartbeat_status
from app.agents.action_planner import format_action_plan_context
from app.agents.answer_guard import guard_ollama_answer
from app.agents.intent_router import format_intent_context
from app.agents.understanding import build_understanding_frame, format_understanding_context
from app.integrations.gmail_chat import (
    build_gmail_chat_response,
    format_gmail_message_list,
    wants_gmail_auto_reply,
    wants_gmail_inspect,
    wants_gmail_open,
    wants_gmail_list,
    wants_gmail_reply_audit,
    wants_gmail_reply_draft,
)
from app.integrations.gmail_client import GmailIntegrationError
from app.integrations.browser_assistant import BrowserAssistError, open_assisted_browser_from_message
from app.integrations.browser_actions import BrowserActionError, open_browser_from_message
from app.integrations.spotify_assistant import SpotifyAssistError, open_spotify_from_message
from app.integrations.desktop_chat import DesktopChatError, execute_desktop_control_from_message
from app.integrations.cursor_agent_setup import (
    CursorAgentSetupError,
    format_cursor_agent_setup_response,
    setup_cursor_agent,
    wants_cursor_agent_setup,
)
from app.integrations.beeper_assistant import (
    BeeperAssistantError,
    beeper_response_has_useful_content,
    build_beeper_chat_response,
)
from app.integrations.stitch_design import (
    StitchDesignError,
    build_stitch_prompt,
    format_stitch_design_response,
    prepare_stitch_design,
    wants_stitch_design,
)
from app.integrations.google_setup_chat import (
    build_calendar_events_response,
    build_google_setup_response,
    wants_calendar_events,
    wants_google_account_setup,
)
from app.integrations.linkedin_assistant import (
    LinkedInAssistantError,
    build_linkedin_chat_response,
    wants_linkedin_activity,
    wants_linkedin_browser_post,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.memory_store import (
    MemoryStoreError,
    add_memory,
    detect_auto_memory_candidate,
    detect_explicit_memory_request,
    detect_operating_lesson_candidate,
    memory_to_dict,
)
from app.memory.obsidian_store import ObsidianMemoryError, mirror_memory_to_obsidian
from app.memory.obsidian_store import obsidian_status
from app.projects.project_chat import (
    ProjectStoreError,
    attach_recent_project_context,
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
from app.screen.visual_action import (
    VisualActionError,
    analyze_visual_action,
    format_visual_action_response,
    wants_visual_action,
)
from app.screen.screen_navigator import (
    ScreenNavigationError,
    format_screen_navigation_response,
    navigate_screen,
    wants_screen_navigation,
)
from app.screen.screen_watcher import latest_screen_context
from app.self_improvement.loop import (
    SelfImproveError,
    detect_self_improvement_request,
    execute_self_improvement_loop,
    format_self_improvement_response,
)
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
    "nouvelle idee de projet",
    "idee de projet",
    "j'ai une idee de projet",
    "jai une idee de projet",
    "j'ai une nouvelle idee",
    "jai une nouvelle idee",
    "cree un projet",
    "creer un projet",
    "lance un projet",
    "demarre un projet",
    "prepare un projet",
    "project factory",
)


BAD_TOOL_REFUSAL_MARKERS = (
    "je suis une assistante virtuelle",
    "je ne peux pas ouvrir des applications",
    "je ne peux pas ouvrir d'applications",
    "je ne peux pas interagir avec votre ordinateur",
)


def _remove_bad_tool_refusal(answer: str, user_message: str) -> str:
    normalized_answer = answer.lower()
    if not any(marker in normalized_answer for marker in BAD_TOOL_REFUSAL_MARKERS):
        return answer

    normalized_request = user_message.lower()
    if any(marker in normalized_request for marker in ("ouvre", "ouvrir", "brave", "gmail", "mail", "ecran")):
        return (
            "Je ne dois pas repondre comme une IA sans outils. "
            "Pour cette demande, je dois d'abord chercher l'outil local adapte "
            "(Gmail, Brave, lecture d'ecran ou action locale). "
            "Si aucun outil n'est disponible, je dois dire la limite exacte au lieu d'inventer."
        )
    return answer


def _should_attach_project_context(message: str) -> bool:
    normalized = message.lower()
    if any(marker in normalized for marker in ("cursor", "codex", "projet", "code", "bug", "readme", "branche", "pr ")):
        return True
    return bool(re.search(r"\b(?:repo|repository)\b", normalized))


def _should_create_project_factory_plan(message: str) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", message.lower())
        if not unicodedata.combining(char)
    )
    normalized = " ".join(normalized.split())
    if any(marker in normalized for marker in PROJECT_FACTORY_MARKERS):
        return True
    return bool(
        re.search(
            r"\b(?:cree|creer|lance|demarre|prepare|monte|setup|scaffold|initialise)\b"
            r".{0,80}\b(?:projet|repo|repository|workspace|application|app|saas|site|outil|mvp)\b",
            normalized,
        )
    )


def _wants_force_google_reconnect(message: str) -> bool:
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFKD", message.lower())
        if not unicodedata.combining(char)
    )
    return any(marker in normalized for marker in ("reconnect", "regenere", "regenerer", "nouveau token", "invalid_grant"))


def _mirror_memory(memory: object) -> None:
    try:
        mirror_memory_to_obsidian(memory)
    except ObsidianMemoryError:
        pass


def _blocked_problem_payload(
    message: str,
    understanding: Any,
    tool: str,
    reason: str,
    trusted_actions: bool,
    channel: str,
    next_actions: tuple[str, ...] = (),
    pending_action: dict[str, object] | None = None,
) -> dict[str, Any]:
    content = build_direct_problem_solver_response(
        message,
        understanding,
        tool=tool,
        reason=reason,
        trusted_actions=trusted_actions,
        channel=channel,
        next_actions=next_actions,
    )
    return {
        "message": {
            "role": "assistant",
            "content": content,
            "cognitive_trace": build_reasoning_trace(
                understanding,
                selected_route=str(getattr(understanding, "action_plan").route),
            ),
        },
        "saved_memory": None,
        "pending_action": pending_action,
    }


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

    news_markers = (
        "news",
        "actu",
        "actus",
        "actualite",
        "actualites",
        "quoi de neuf",
        "dernieres infos",
        "dernieres nouvelles",
    )
    if any(marker in normalized for marker in news_markers):
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
    channel: str = "web",
) -> dict[str, Any]:
    if not safe_messages or safe_messages[-1]["role"] != "user":
        raise ChatServiceError("La conversation doit se terminer par un message utilisateur.")

    saved_memory = None
    latest_user_message = safe_messages[-1]["content"]
    conversation_context = safe_messages[:-1]
    understanding = build_understanding_frame(
        latest_user_message,
        conversation_context=conversation_context,
        trusted_actions=trusted_actions,
    )
    cognitive_context = build_cognitive_context(
        latest_user_message,
        conversation_context=conversation_context,
        frame=understanding,
    )
    understanding = attach_cognitive_context(understanding, cognitive_context)
    if wants_google_account_setup(latest_user_message):
        return {
            "message": {
                "role": "assistant",
                "content": build_google_setup_response(
                    trusted_actions=trusted_actions,
                    intent_context="",
                    force_reconnect=_wants_force_google_reconnect(latest_user_message),
                ),
            },
            "saved_memory": None,
            "pending_action": None,
        }

    understanding = await refine_understanding_with_ollama(
        latest_user_message,
        conversation_context=conversation_context,
        base_frame=understanding,
        trusted_actions=trusted_actions,
    )
    user_intent = understanding.intent
    action_plan = understanding.action_plan
    intent_context = format_intent_context(user_intent)
    context_blocks: list[str] = [
        format_cognitive_context(cognitive_context),
        format_understanding_context(understanding),
        format_action_plan_context(action_plan),
        build_ml_adaptation_context(latest_user_message, understanding),
    ]

    if understanding.clarification_question and understanding.safety_level in {"external_draft", "critical"}:
        return {
            "message": {
                "role": "assistant",
                "content": understanding.clarification_question,
            },
            "saved_memory": None,
            "pending_action": None,
        }

    try:
        if trusted_actions:
            screen_context = latest_screen_context()
            if screen_context:
                context_blocks.append(screen_context)

        if action_plan.route == "screen_read":
            if not trusted_actions:
                return _blocked_problem_payload(
                    latest_user_message,
                    understanding,
                    tool="screen_reader",
                    reason=(
                        "Lire l'ecran expose des donnees privees; le canal courant "
                        "n'est pas marque comme PC local ou Telegram autorise."
                    ),
                    trusted_actions=trusted_actions,
                    channel=channel,
                    next_actions=(
                        "relancer depuis le PC local ou Telegram autorise",
                        "decrire ou copier-coller l'erreur visible pour que je la diagnostique",
                    ),
                )
            if wants_screen_navigation(latest_user_message) or wants_visual_action(latest_user_message):
                navigation_result = await navigate_screen(latest_user_message)
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"{intent_context}\n\n"
                            f"{format_screen_navigation_response(navigation_result)}"
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

        if action_plan.route == "terminal_error" or looks_like_terminal_error(latest_user_message):
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

        if action_plan.route == "google_oauth_setup":
            return {
                "message": {
                    "role": "assistant",
                    "content": build_google_setup_response(
                        trusted_actions=trusted_actions,
                        intent_context="",
                        force_reconnect=_wants_force_google_reconnect(latest_user_message),
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if action_plan.route == "cursor_agent_setup" or wants_cursor_agent_setup(latest_user_message):
            setup_result = setup_cursor_agent(
                auto_install=trusted_actions,
                open_docs_on_block=trusted_actions,
            )
            return {
                "message": {
                    "role": "assistant",
                    "content": format_cursor_agent_setup_response(setup_result),
                    "cognitive_trace": build_reasoning_trace(
                        understanding,
                        selected_route="cursor_agent_setup",
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if action_plan.route == "project_factory" or _should_create_project_factory_plan(latest_user_message):
            if not trusted_actions:
                return _blocked_problem_payload(
                    latest_user_message,
                    understanding,
                    tool="project_factory",
                    reason=(
                        "La creation de workspace/repo demande une session fiable "
                        "avant de piloter le PC."
                    ),
                    trusted_actions=trusted_actions,
                    channel=channel,
                    next_actions=(
                        "preparer un brief et un prompt projet sans toucher au PC",
                        "relancer depuis Telegram autorise pour executer automatiquement",
                    ),
                )

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
                        "cognitive_trace": build_reasoning_trace(
                            understanding,
                            selected_route="project_factory",
                        ),
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
                    "cognitive_trace": build_reasoning_trace(
                        understanding,
                        selected_route="project_factory",
                    ),
                },
                "saved_memory": None,
                "pending_action": action_to_dict(first_action),
            }

        if detect_self_improvement_request(latest_user_message):
            if not trusted_actions:
                return _blocked_problem_payload(
                    latest_user_message,
                    understanding,
                    tool="self_improvement",
                    reason="Modifier durablement le comportement d'Eva demande une session fiable.",
                    trusted_actions=trusted_actions,
                    channel=channel,
                    next_actions=(
                        "transformer la demande en note Obsidian ou souvenir non executif",
                        "relancer depuis le PC local ou Telegram autorise pour creer la tache",
                    ),
                )

            result = execute_self_improvement_loop(
                latest_user_message,
                source="chat",
                trusted_actions=True,
            )
            return {
                "message": {
                    "role": "assistant",
                    "content": format_self_improvement_response(result),
                },
                "saved_memory": result.get("saved_memory"),
                "pending_action": None,
            }

        pending_action = create_pending_action_from_message(latest_user_message)
        if pending_action:
            if not trusted_actions:
                return _blocked_problem_payload(
                    latest_user_message,
                    understanding,
                    tool="action_store",
                    reason="Action locale detectee depuis un canal non fiable.",
                    trusted_actions=trusted_actions,
                    channel=channel,
                    next_actions=(
                        "preparer le plan d'action sans execution",
                        "relancer depuis Telegram autorise ou le PC local",
                    ),
                )

            if settings.eva_auto_execute_actions:
                try:
                    execution = execute_action(pending_action.id, require_approval=False)
                except ActionExecutionError as exc:
                    return _blocked_problem_payload(
                        latest_user_message,
                        understanding,
                        tool="action_executor",
                        reason=f"Action #{pending_action.id} protegee: {exc}",
                        trusted_actions=trusted_actions,
                        channel=channel,
                        next_actions=(
                            "tenter une version brouillon ou lecture seule",
                            "creer une action en attente si le risque reste eleve",
                            "ajuster le flag local seulement si Victor assume ce niveau d'autonomie",
                        ),
                        pending_action=action_to_dict(pending_action),
                    )
                action_payload = execution.get("action")
                executed = bool(execution.get("executed"))
                result_text = ""
                if isinstance(action_payload, dict):
                    result_text = str(action_payload.get("result", "")).strip()

                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            f"Action #{pending_action.id} executee automatiquement: {pending_action.title}.\n"
                            f"Statut: {'executee' if executed else 'echec'}\n\n"
                            f"{result_text[:3000]}"
                        ).strip(),
                    },
                    "saved_memory": None,
                    "pending_action": action_payload if isinstance(action_payload, dict) else None,
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
    except (
        ActionExecutionError,
        ActionStoreError,
        CursorAgentSetupError,
        ProjectFactoryError,
        ScreenReaderError,
        SelfImproveError,
    ) as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if not trusted_actions and _quick_status_requires_trusted_access(latest_user_message):
            return _blocked_problem_payload(
                latest_user_message,
                understanding,
                tool="local_status",
                reason="La demande consulte l'etat local d'Eva depuis un canal non fiable.",
                trusted_actions=trusted_actions,
                channel=channel,
                next_actions=(
                    "donner une explication generale sans exposer l'etat local",
                    "relancer depuis le PC local ou Telegram autorise pour lire le statut reel",
                ),
            )

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

    cognitive_result = await run_cognitive_loop(
        latest_user_message,
        understanding,
        trusted_actions=trusted_actions,
        channel=channel,
    )
    if cognitive_result.handled and cognitive_result.message:
        return {
            "message": cognitive_result.message,
            "saved_memory": None,
            "pending_action": None,
        }

    try:
        gmail_context_message = latest_user_message
        if understanding.primary_domain == "gmail" and understanding.context_focus:
            gmail_context_message = (
                f"{latest_user_message}\n\n"
                f"Contexte recent utile:\n{understanding.context_focus}"
            )

        calendar_requested = (
            action_plan.route == "calendar_read"
            or understanding.primary_domain == "calendar"
            or wants_calendar_events(latest_user_message)
        )
        gmail_requested = (
            action_plan.route in {"gmail_read", "gmail_reply_audit", "gmail_reply_draft"}
            or understanding.primary_domain == "gmail"
            or wants_gmail_inspect(gmail_context_message)
            or wants_gmail_auto_reply(gmail_context_message)
            or wants_gmail_open(gmail_context_message)
            or wants_gmail_list(gmail_context_message)
            or wants_gmail_reply_audit(gmail_context_message)
            or wants_gmail_reply_draft(gmail_context_message)
        )

        if not trusted_actions and (calendar_requested or gmail_requested):
            return _blocked_problem_payload(
                latest_user_message,
                understanding,
                tool="google_private_data",
                reason="Gmail et Google Calendar contiennent des donnees privees; le canal courant n'est pas fiable.",
                trusted_actions=trusted_actions,
                channel=channel,
                next_actions=(
                    "preparer la methode de tri ou de brouillon sans lire les donnees",
                    "relancer depuis Telegram autorise ou le PC local pour lire les vrais mails",
                ),
            )

        if calendar_requested and gmail_requested and action_plan.route != "gmail_reply_draft":
            sections = []
            try:
                sections.append(format_gmail_message_list())
            except GmailIntegrationError as exc:
                sections.append(f"Source: Gmail API.\nGmail indisponible: {exc}")
            try:
                sections.append(build_calendar_events_response(days=7))
            except GmailIntegrationError as exc:
                sections.append(f"Source: Google Calendar API.\nCalendar indisponible: {exc}")
            return {
                "message": {
                    "role": "assistant",
                    "content": "\n\n---\n\n".join(sections),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if calendar_requested:
            return {
                "message": {
                    "role": "assistant",
                    "content": build_calendar_events_response(days=7),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        gmail_response = await build_gmail_chat_response(
            gmail_context_message,
            force_list=action_plan.route == "gmail_read",
        )
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
        spotify_response = open_spotify_from_message(latest_user_message) if trusted_actions else None
        if spotify_response:
            return {
                "message": {
                    "role": "assistant",
                    "content": spotify_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if trusted_actions and wants_visual_action(latest_user_message):
            if wants_screen_navigation(latest_user_message):
                navigation_result = await navigate_screen(latest_user_message)
                return {
                    "message": {
                        "role": "assistant",
                        "content": format_screen_navigation_response(navigation_result),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }
            visual_result = await analyze_visual_action(latest_user_message, execute=True)
            return {
                "message": {
                    "role": "assistant",
                    "content": format_visual_action_response(visual_result),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        desktop_response = (
            execute_desktop_control_from_message(latest_user_message)
            if trusted_actions
            else None
        )
        if desktop_response:
            return {
                "message": {
                    "role": "assistant",
                    "content": desktop_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }

        beeper_response = await build_beeper_chat_response(latest_user_message) if trusted_actions else None
        if beeper_response and beeper_response_has_useful_content(beeper_response):
            return {
                "message": {
                    "role": "assistant",
                    "content": beeper_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }

        if wants_stitch_design(latest_user_message):
            if trusted_actions:
                stitch_package = prepare_stitch_design(latest_user_message)
                return {
                    "message": {
                        "role": "assistant",
                        "content": format_stitch_design_response(stitch_package),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }

            prompt = build_stitch_prompt(latest_user_message)
            return {
                "message": {
                    "role": "assistant",
                    "content": (
                        "Je peux preparer un prompt Google Stitch depuis le PC local ou Telegram autorise.\n\n"
                        f"Prompt Stitch propose:\n\n```text\n{prompt}\n```"
                    ),
                },
                "saved_memory": None,
                "pending_action": None,
            }

        browser_assist_response = open_assisted_browser_from_message(latest_user_message) if trusted_actions else None
        if browser_assist_response:
            return {
                "message": {
                    "role": "assistant",
                    "content": browser_assist_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }

        browser_response = open_browser_from_message(latest_user_message) if trusted_actions else None
        if browser_response:
            return {
                "message": {
                    "role": "assistant",
                    "content": browser_response,
                },
                "saved_memory": None,
                "pending_action": None,
            }
    except (
        BrowserActionError,
        BrowserAssistError,
        SpotifyAssistError,
        DesktopChatError,
        BeeperAssistantError,
        VisualActionError,
        ScreenNavigationError,
        StitchDesignError,
    ) as exc:
        raise ChatServiceError(str(exc)) from exc

    try:
        if not trusted_actions and (
            wants_linkedin_browser_post(latest_user_message) or wants_linkedin_activity(latest_user_message)
        ):
            return _blocked_problem_payload(
                latest_user_message,
                understanding,
                tool="linkedin_assistant",
                reason="LinkedIn contient des donnees de compte; le canal courant n'est pas fiable.",
                trusted_actions=trusted_actions,
                channel=channel,
                next_actions=(
                    "preparer un brouillon ou une strategie sans ouvrir le compte",
                    "relancer depuis Telegram autorise ou le PC local pour naviguer dans Brave",
                ),
            )

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
        if action_plan.route == "cursor_work" or detect_cursor_prompt_request(latest_user_message):
            cursor_context_message = attach_recent_project_context(
                latest_user_message,
                understanding.context_focus,
            )

            if trusted_actions:
                return {
                    "message": {
                        "role": "assistant",
                        "content": build_cursor_work_session_response(cursor_context_message),
                    },
                    "saved_memory": None,
                    "pending_action": None,
                }

            return {
                "message": {
                    "role": "assistant",
                    "content": build_chat_cursor_prompt_response(cursor_context_message),
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
            memory_candidate = detect_operating_lesson_candidate(
                latest_user_message
            ) or detect_auto_memory_candidate(latest_user_message)
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
        answer = _remove_bad_tool_refusal(answer, latest_user_message)
        answer = guard_ollama_answer(answer, latest_user_message)
        if settings.eva_problem_solver_enabled and looks_like_passive_refusal(answer):
            answer = build_passive_refusal_recovery(latest_user_message)
    except OllamaClientError as exc:
        raise ChatServiceError(str(exc)) from exc

    return {
        "message": {
            "role": "assistant",
            "content": answer,
            "cognitive_trace": build_reasoning_trace(understanding)
            if settings.eva_reasoning_force_structured_trace
            else None,
        },
        "saved_memory": saved_memory,
        "pending_action": None,
    }

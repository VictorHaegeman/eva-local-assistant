from typing import Literal

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.actions.action_store import (
    ActionStoreError,
    action_to_dict,
    create_action,
    delete_action,
    get_action,
    init_action_store,
    list_actions,
    update_action_status,
)
from app.actions.executor import ActionExecutionError, execute_action
from app.agents.modes import AgentModeName, list_modes
from app.briefs.brief_store import BriefStoreError, brief_to_dict, get_latest_brief, init_brief_store
from app.briefs.daily_launch import DailyLaunchError, get_daily_launch_brief
from app.briefs.rss_brief import RssBriefError, ensure_sources_file, generate_morning_brief
from app.briefs.smart_brief import SmartBriefError, generate_smart_brief_payload
from app.chat_service import ChatServiceError, process_chat_messages
from app.config import settings
from app.agents.understanding import build_understanding_frame, understanding_to_dict
from app.cognition.context import attach_cognitive_context, build_cognitive_context
from app.cognition.structured_interpreter import refine_understanding_with_ollama
from app.agents.operator_journal import (
    OperatorJournalError,
    init_operator_journal,
    list_operator_ticks,
    operator_status,
    operator_tick_to_dict,
    record_operator_tick,
)
from app.doctor.autonomy_readiness import autonomy_readiness
from app.doctor.diagnostics import run_doctor
from app.files.local_files import (
    LocalFileError,
    ensure_allowed_paths_file,
    list_directory,
    read_text_file,
    roots_to_dicts,
    search_files,
)
from app.heartbeat.scheduler import (
    HeartbeatError,
    ensure_heartbeats_file,
    heartbeat_status,
    run_heartbeat_job,
    start_heartbeat_background_task,
)
from app.integrations.gmail_client import (
    GmailIntegrationError,
    create_gmail_reply_draft,
    find_sent_examples,
    format_email_for_prompt,
    format_sent_examples_for_prompt,
    get_gmail_message,
    gmail_status,
    list_gmail_messages,
    message_to_dict,
)
from app.integrations.gmail_chat import parse_reply_draft
from app.integrations.gmail_auth import GmailAuthLaunchError, start_gmail_oauth_flow
from app.integrations.google_calendar_client import (
    calendar_event_to_dict,
    calendar_status,
    list_calendar_events,
)
from app.integrations.inbox_smart import collect_inbox_signals
from app.integrations.browser import open_url
from app.integrations.browser_assistant import (
    BrowserAssistError,
    detect_browser_assist,
    open_assisted_browser_from_message,
)
from app.integrations.spotify_assistant import (
    SpotifyAssistError,
    detect_spotify_request,
    open_spotify_from_message,
)
from app.integrations.beeper_assistant import (
    BeeperAssistantError,
    build_beeper_chat_response,
    open_beeper,
    wants_beeper_reply,
)
from app.integrations.stitch_design import (
    StitchDesignError,
    build_stitch_prompt,
    format_stitch_design_response,
    prepare_stitch_design,
    wants_stitch_design,
)
from app.integrations.desktop_automation import (
    DesktopAutomationError,
    click_pixel,
    click_ratio,
    desktop_status,
    press_key,
)
from app.integrations.linkedin_assistant import (
    LinkedInAssistantError,
    draft_linkedin_comment,
    draft_linkedin_post,
    ensure_linkedin_file,
    linkedin_status,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.memory_store import (
    MemoryStoreError,
    add_memory,
    delete_memory,
    init_memory_store,
    list_memories,
    memory_to_dict,
)
from app.memory.cluster_store import list_memory_clusters
from app.memory.embedding_store import (
    EmbeddingStoreError,
    embedding_status,
    rebuild_memory_embeddings,
)
from app.memory.memory_router import route_memory
from app.memory.chat_history_store import (
    ChatHistoryError,
    append_chat_exchange,
    chat_message_to_dict,
    chat_session_to_dict,
    get_chat_messages,
    init_chat_history_store,
    list_chat_sessions,
)
from app.memory.obsidian_store import (
    ObsidianMemoryError,
    ensure_obsidian_vault,
    mirror_memory_to_obsidian,
    open_obsidian_vault,
    obsidian_status,
    sync_memories_to_obsidian,
)
from app.memory.profile_store import ProfileStoreError, ensure_profile_file, load_profile
from app.messaging.telegram_bot import start_telegram_background_task, telegram_config_status
from app.projects.project_store import (
    ProjectStoreError,
    build_branch_plan,
    build_cursor_prompt,
    ensure_projects_file,
    load_projects,
    project_tree,
    read_project_file,
)
from app.project_factory.planner import (
    ProjectFactoryError,
    build_project_plan,
    create_project_factory_actions,
)
from app.project_factory.automation import (
    auto_execute_project_factory_actions,
    project_factory_auto_status,
)
from app.project_factory.agent_runner import list_project_factory_agent_events
from app.projects.task_store import (
    TaskStoreError,
    create_task,
    delete_task,
    init_task_store,
    list_tasks,
    task_to_dict,
)
from app.security.action_policy import autonomy_policy_text, can_auto_execute, policy_levels
from app.security.api_auth import is_request_trusted, require_sensitive_access
from app.skills.registry import ensure_skills_file, list_skills
from app.social.instagram_public import (
    InstagramPublicError,
    ensure_socials_file,
    fetch_instagram_public_snapshots,
    instagram_status,
)
from app.screen.screen_reader import (
    ScreenReaderError,
    analyze_screen,
    capture_screen,
    screen_status,
)
from app.screen.visual_action import VisualActionError, analyze_visual_action
from app.screen.screen_watcher import (
    latest_screen_analysis,
    run_screen_watch_once,
    start_screen_watch_background_task,
)
from app.self_improvement.loop import (
    SelfImproveError,
    build_self_improvement_plan,
    detect_self_improvement_request,
    execute_self_improvement_loop,
    format_self_improvement_response,
    list_self_improvement_events,
    self_improvement_plan_to_dict,
)
from app.terminal.terminal_doctor import (
    TerminalDoctorError,
    analyze_terminal_error,
    diagnosis_to_dict,
    launch_terminal_fix,
)
from app.tools.registry import list_tools
from app.web.web_search import WebSearchError, format_web_results, search_web


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)
    web_preview: dict[str, object] | None = None
    cognitive_trace: dict[str, object] | None = None


class ChatRequest(BaseModel):
    messages: list[Message] = Field(default_factory=list, max_length=50)
    mode: AgentModeName = "chat"
    session_id: str = Field(default="", max_length=120)


class UnderstandRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    context: list[Message] = Field(default_factory=list, max_length=20)


class SelfImproveRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    source: str = Field(default="api", max_length=80)
    auto_launch_agent: bool | None = None


class ChatResponse(BaseModel):
    message: Message
    saved_memory: dict[str, object] | None = None
    pending_action: dict[str, object] | None = None
    session_id: str | None = None


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    category: str = Field(default="general", min_length=1, max_length=40)


class MemoryRouteRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=8, ge=1, le=20)


class MemoryEmbeddingRebuildRequest(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)


class FileReadRequest(BaseModel):
    root: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=500)


class FileSummaryRequest(FileReadRequest):
    instruction: str = Field(
        default="Resume ce fichier clairement et donne les points importants.",
        min_length=1,
        max_length=500,
    )


class ProjectFileReadRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)


class CursorPromptRequest(BaseModel):
    task: str = Field(min_length=1, max_length=5000)


class BranchPlanRequest(BaseModel):
    branch_name: str = Field(min_length=1, max_length=120)


class TerminalErrorRequest(BaseModel):
    error: str = Field(min_length=1, max_length=20_000)


class TerminalErrorAnalyzeRequest(BaseModel):
    error: str = Field(min_length=1, max_length=20_000)
    auto_fix: bool = False


class TerminalFixRequest(BaseModel):
    fix_key: str = Field(min_length=1, max_length=120)


class ProjectTaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=2000)
    priority: Literal["low", "normal", "high"] = "normal"


class ProjectDraftRequest(BaseModel):
    instruction: str = Field(default="", max_length=5000)


class ProjectFactoryPlanRequest(BaseModel):
    idea: str = Field(min_length=8, max_length=8000)
    project_name: str = Field(default="", max_length=120)


class ActionCreateRequest(BaseModel):
    action_type: Literal[
        "command",
        "read_file",
        "write_file",
        "delete_path",
        "codex_prompt",
        "git_initial_commit",
        "git_push",
    ]
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    payload: dict[str, object] = Field(default_factory=dict)


class CommandActionRequest(BaseModel):
    command: str = Field(min_length=1, max_length=5000)
    cwd: str = Field(default="", max_length=1000)
    title: str = Field(default="Executer une commande locale", max_length=200)


class CodexPromptActionRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    project: str = Field(default="", max_length=200)
    title: str = Field(default="Preparer un prompt Cursor/Codex", max_length=200)


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=8)


class BrowserOpenTabsRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=8)


class BrowserAssistRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class StitchDesignRequest(BaseModel):
    request: str = Field(min_length=1, max_length=8000)
    project_name: str = Field(default="Projet frontend", max_length=120)
    design_direction: str = Field(default="", max_length=2000)
    open_in_browser: bool = True


class SpotifyOpenRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class BeeperRequest(BaseModel):
    message: str = Field(
        default="Lis mes messages Beeper visibles et fais-moi un debrief.",
        min_length=1,
        max_length=2000,
    )


class DesktopClickRequest(BaseModel):
    x: int = Field(ge=0, le=20000)
    y: int = Field(ge=0, le=20000)


class DesktopClickRatioRequest(BaseModel):
    x_ratio: float = Field(ge=0.0, le=1.0)
    y_ratio: float = Field(ge=0.0, le=1.0)


class DesktopKeyRequest(BaseModel):
    key: Literal[
        "enter",
        "space",
        "tab",
        "escape",
        "media_play_pause",
        "media_next",
        "media_previous",
        "volume_up",
        "volume_down",
        "volume_mute",
    ]
    presses: int = Field(default=1, ge=1, le=20)


class DailyLaunchRequest(BaseModel):
    force: bool = False


class ScreenAnalyzeRequest(BaseModel):
    instruction: str = Field(default="", max_length=2000)
    auto_fix: bool = False


class VisualActionRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    execute: bool = True


class GmailReplyDraftRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(
        default="Redige une reponse claire, directe et cordiale.",
        min_length=1,
        max_length=5000,
    )
    create_in_gmail: bool = True
    open_in_browser: bool = True


class LinkedInPostDraftRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=5000)
    angle: str = Field(default="", max_length=1000)
    audience: str = Field(default="", max_length=1000)
    format_name: str = Field(default="post court", min_length=1, max_length=80)


class LinkedInCommentDraftRequest(BaseModel):
    post_context: str = Field(min_length=1, max_length=8000)
    intent: str = Field(default="", max_length=1000)


app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

ensure_profile_file()
init_memory_store()
ensure_obsidian_vault()
ensure_allowed_paths_file()
ensure_sources_file()
ensure_projects_file()
ensure_heartbeats_file()
ensure_linkedin_file()
ensure_socials_file()
ensure_skills_file()
init_brief_store()
init_task_store()
init_action_store()
init_chat_history_store()
init_operator_journal()

telegram_task: asyncio.Task[None] | None = None
heartbeat_task: asyncio.Task[None] | None = None
screen_watch_task: asyncio.Task[None] | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global heartbeat_task, screen_watch_task, telegram_task
    telegram_task = start_telegram_background_task()
    heartbeat_task = start_heartbeat_background_task()
    screen_watch_task = start_screen_watch_background_task()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if telegram_task:
        telegram_task.cancel()
    if heartbeat_task:
        heartbeat_task.cancel()
    if screen_watch_task:
        screen_watch_task.cancel()


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "model": settings.ollama_model,
    }


@app.get("/messaging/telegram/status", dependencies=[Depends(require_sensitive_access)])
async def telegram_status() -> dict[str, object]:
    return telegram_config_status()


@app.get("/gmail/status", dependencies=[Depends(require_sensitive_access)])
async def gmail_config_status() -> dict[str, object]:
    return gmail_status()


@app.post("/gmail/connect", dependencies=[Depends(require_sensitive_access)])
async def gmail_connect(force_reconnect: bool = Query(default=False)) -> dict[str, object]:
    try:
        return start_gmail_oauth_flow(force_reconnect=force_reconnect)
    except GmailAuthLaunchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/calendar/status", dependencies=[Depends(require_sensitive_access)])
async def google_calendar_status() -> dict[str, object]:
    return calendar_status()


@app.get("/calendar/events", dependencies=[Depends(require_sensitive_access)])
async def google_calendar_events(
    days: int = Query(default=7, ge=1, le=30),
    max_results: int = Query(default=10, ge=1, le=25),
) -> dict[str, object]:
    try:
        events = list_calendar_events(days=days, max_results=max_results)
    except GmailIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "events": [calendar_event_to_dict(event) for event in events],
    }


@app.get("/linkedin/status", dependencies=[Depends(require_sensitive_access)])
async def linkedin_config_status() -> dict[str, object]:
    return linkedin_status()


@app.get("/social/instagram/status", dependencies=[Depends(require_sensitive_access)])
async def instagram_config_status() -> dict[str, object]:
    return instagram_status()


@app.get("/social/instagram/public-snapshot", dependencies=[Depends(require_sensitive_access)])
async def instagram_public_snapshot() -> dict[str, object]:
    try:
        return await fetch_instagram_public_snapshots()
    except InstagramPublicError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/heartbeat/status", dependencies=[Depends(require_sensitive_access)])
async def heartbeat_config_status() -> dict[str, object]:
    return heartbeat_status()


@app.post("/heartbeat/run/{job_key}", dependencies=[Depends(require_sensitive_access)])
async def heartbeat_run(job_key: str) -> dict[str, object]:
    try:
        return await run_heartbeat_job(job_key)
    except HeartbeatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RssBriefError, BriefStoreError, OllamaClientError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/doctor")
async def doctor() -> dict[str, object]:
    return await run_doctor()


@app.get("/agents/modes")
async def agent_modes() -> dict[str, object]:
    return {
        "modes": list_modes(),
    }


@app.get("/tools")
async def tools() -> dict[str, object]:
    return {
        "tools": list_tools(),
    }


@app.get("/skills")
async def skills() -> dict[str, object]:
    return {
        "skills": list_skills(),
    }


@app.get("/autonomy", dependencies=[Depends(require_sensitive_access)])
async def autonomy() -> dict[str, object]:
    return {
        "mode": settings.eva_autonomy_mode,
        "auto_execute_actions": settings.eva_auto_execute_actions,
        "auto_execute_commands": settings.eva_auto_execute_commands,
        "auto_write_files": settings.eva_auto_write_files,
        "allow_write_any_path": settings.eva_allow_write_any_path,
        "allow_auto_delete": settings.eva_allow_auto_delete,
        "allow_auto_git_push": settings.eva_allow_auto_git_push,
        "allow_auto_external_send": settings.eva_allow_auto_external_send,
        "policy": autonomy_policy_text(),
        "levels": policy_levels(),
        "project_factory": project_factory_auto_status(),
        "auto_without_confirmation": [
            "lecture/analyse dans les dossiers configures",
            "recherche web gratuite",
            "lecture Gmail si OAuth local est configure",
            "brouillon LinkedIn sans publication",
            "heartbeat local si active",
            "brouillon de reponse email sans envoi",
            "resume",
            "creation de taches locales",
            "preparation de prompts Cursor/Codex",
            "ouverture de sites et apps supportees",
            "commandes locales non critiques",
            "creation de workspace projet",
            "copie presse-papiers et ouverture Cursor",
            "commit Git local initial",
            "creation de repo GitHub si gh est connecte",
            "self-improvement: memoire, tache locale et prompt Cursor",
        ],
        "protected_even_in_operator": [
            "suppression de fichiers sauf EVA_ALLOW_AUTO_DELETE=true",
            "git push sauf EVA_ALLOW_AUTO_GIT_PUSH=true ou EVA_PROJECT_FACTORY_AUTO_PUSH=true",
            "publication",
            "envoi de message",
            "envoi d'email",
            "publication LinkedIn",
            "commandes critiques: reset, clean, delete, shutdown, format, execution policy",
            "auto-modification par cursor-agent sauf EVA_SELF_IMPROVE_AUTO_CURSOR_AGENT=true ou demande explicite",
        ],
    }


@app.get("/autonomy/readiness", dependencies=[Depends(require_sensitive_access)])
async def autonomy_readiness_route() -> dict[str, object]:
    return autonomy_readiness()


@app.get("/operator/status", dependencies=[Depends(require_sensitive_access)])
async def operator_journal_status() -> dict[str, object]:
    try:
        return operator_status()
    except OperatorJournalError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/operator/ticks", dependencies=[Depends(require_sensitive_access)])
async def operator_journal_ticks(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
    try:
        ticks = list_operator_ticks(limit=limit)
    except OperatorJournalError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ticks": [operator_tick_to_dict(tick) for tick in ticks],
    }


@app.get("/profile", dependencies=[Depends(require_sensitive_access)])
async def profile() -> dict[str, object]:
    try:
        loaded_profile = load_profile()
    except ProfileStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "loaded": True,
        "profile": loaded_profile,
    }


@app.get("/memories", dependencies=[Depends(require_sensitive_access)])
async def memories() -> dict[str, object]:
    try:
        loaded_memories = list_memories()
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "loaded": True,
        "memories": [memory_to_dict(memory) for memory in loaded_memories],
    }


@app.get("/memory/clusters", dependencies=[Depends(require_sensitive_access)])
async def memory_clusters() -> dict[str, object]:
    return {
        "clusters": list_memory_clusters(),
    }


@app.post("/memory/route", dependencies=[Depends(require_sensitive_access)])
async def memory_route(request: MemoryRouteRequest) -> dict[str, object]:
    context = route_memory(request.query, limit=request.limit)
    return {
        "query": request.query,
        "intent": {
            "name": context.intent_name,
            "summary": context.intent_summary,
        },
        "clusters": [
            {
                "key": route.cluster.key,
                "label": route.cluster.label,
                "score": route.score,
            }
            for route in context.clusters
        ],
        "vector_available": context.vector_available,
        "vector_error": context.vector_error,
        "results": [
            {
                "memory": memory_to_dict(result.memory),
                "score": result.score,
                "cluster_key": result.cluster_key,
                "signals": result.signals,
            }
            for result in context.results
        ],
    }


@app.get("/memory/embeddings/status", dependencies=[Depends(require_sensitive_access)])
async def memory_embeddings_status() -> dict[str, object]:
    try:
        return embedding_status()
    except EmbeddingStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/memory/embeddings/rebuild", dependencies=[Depends(require_sensitive_access)])
async def memory_embeddings_rebuild(request: MemoryEmbeddingRebuildRequest) -> dict[str, object]:
    try:
        return rebuild_memory_embeddings(limit=request.limit)
    except EmbeddingStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/chat/history", dependencies=[Depends(require_sensitive_access)])
async def chat_history() -> dict[str, object]:
    try:
        sessions = list_chat_sessions()
    except ChatHistoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "sessions": [chat_session_to_dict(session) for session in sessions],
    }


@app.get("/chat/history/{session_id}", dependencies=[Depends(require_sensitive_access)])
async def chat_history_messages(session_id: str) -> dict[str, object]:
    try:
        messages = get_chat_messages(session_id)
    except ChatHistoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "messages": [chat_message_to_dict(message) for message in messages],
    }


@app.get("/memory/obsidian/status", dependencies=[Depends(require_sensitive_access)])
async def memory_obsidian_status() -> dict[str, object]:
    return obsidian_status()


@app.post("/memory/obsidian/sync", dependencies=[Depends(require_sensitive_access)])
async def memory_obsidian_sync() -> dict[str, object]:
    try:
        loaded_memories = list_memories(limit=200)
        return sync_memories_to_obsidian(loaded_memories)
    except (MemoryStoreError, ObsidianMemoryError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/memory/obsidian/open", dependencies=[Depends(require_sensitive_access)])
async def memory_obsidian_open() -> dict[str, object]:
    try:
        return open_obsidian_vault()
    except ObsidianMemoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/memories", dependencies=[Depends(require_sensitive_access)])
async def create_memory(request: MemoryCreateRequest) -> dict[str, object]:
    try:
        memory = add_memory(request.content, request.category, source="manual")
        mirror_memory_to_obsidian(memory)
    except MemoryStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ObsidianMemoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "saved": True,
        "memory": memory_to_dict(memory),
    }


@app.delete("/memories/{memory_id}", dependencies=[Depends(require_sensitive_access)])
async def remove_memory(memory_id: int) -> dict[str, object]:
    try:
        deleted = delete_memory(memory_id)
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Memoire introuvable.")

    return {
        "deleted": True,
        "id": memory_id,
    }


@app.get("/actions", dependencies=[Depends(require_sensitive_access)])
async def actions(status: str | None = Query(default=None)) -> dict[str, object]:
    try:
        loaded_actions = list_actions(status=status)
    except ActionStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "actions": [action_to_dict(action) for action in loaded_actions],
    }


@app.get("/actions/{action_id}", dependencies=[Depends(require_sensitive_access)])
async def action_detail(action_id: int) -> dict[str, object]:
    try:
        action = get_action(action_id)
    except ActionStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "action": action_to_dict(action),
    }


@app.post("/actions", dependencies=[Depends(require_sensitive_access)])
async def action_create(request: ActionCreateRequest) -> dict[str, object]:
    try:
        action = create_action(
            action_type=request.action_type,
            title=request.title,
            description=request.description,
            payload=request.payload,
        )
        allowed, _reason = can_auto_execute(request.action_type, request.payload)
        if allowed:
            return execute_action(action.id, require_approval=False)
    except ActionStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ActionExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "action": action_to_dict(action),
    }


@app.post("/actions/command", dependencies=[Depends(require_sensitive_access)])
async def action_command_create(request: CommandActionRequest) -> dict[str, object]:
    payload: dict[str, object] = {"command": request.command}
    if request.cwd:
        payload["cwd"] = request.cwd

    try:
        action = create_action(
            action_type="command",
            title=request.title,
            description="Commande locale creee depuis l'API.",
            payload=payload,
        )
        allowed, _reason = can_auto_execute("command", payload)
        if allowed:
            return execute_action(action.id, require_approval=False)
    except ActionStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ActionExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "action": action_to_dict(action),
    }


@app.post("/actions/codex-prompt", dependencies=[Depends(require_sensitive_access)])
async def action_codex_prompt_create(request: CodexPromptActionRequest) -> dict[str, object]:
    try:
        action = create_action(
            action_type="codex_prompt",
            title=request.title,
            description="Prompt Cursor/Codex local, sans appel OpenAI par Eva.",
            payload={"prompt": request.prompt, "project": request.project},
        )
        return execute_action(action.id, require_approval=False)
    except ActionStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ActionExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/actions/{action_id}/approve", dependencies=[Depends(require_sensitive_access)])
async def action_approve(action_id: int) -> dict[str, object]:
    try:
        update_action_status(action_id, "approved")
        return execute_action(action_id)
    except ActionStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ActionExecutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/actions/{action_id}/reject", dependencies=[Depends(require_sensitive_access)])
async def action_reject(action_id: int) -> dict[str, object]:
    try:
        action = update_action_status(action_id, "rejected", "Action rejetee par Victor.")
    except ActionStoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "action": action_to_dict(action),
    }


@app.delete("/actions/{action_id}", dependencies=[Depends(require_sensitive_access)])
async def action_delete(action_id: int) -> dict[str, object]:
    try:
        deleted = delete_action(action_id)
    except ActionStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Action introuvable.")

    return {
        "deleted": True,
        "id": action_id,
    }


@app.get("/files/roots", dependencies=[Depends(require_sensitive_access)])
async def file_roots() -> dict[str, object]:
    try:
        roots = roots_to_dicts()
    except LocalFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "roots": roots,
    }


@app.get("/files/list", dependencies=[Depends(require_sensitive_access)])
async def files_list(
    root: str = Query(..., min_length=1),
    path: str = Query(".", min_length=1),
) -> dict[str, object]:
    try:
        return list_directory(root, path)
    except LocalFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/files/search", dependencies=[Depends(require_sensitive_access)])
async def files_search(
    q: str = Query(..., min_length=1),
    root: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        results = search_files(q, root_name=root)
    except LocalFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "results": results,
    }


@app.post("/files/read", dependencies=[Depends(require_sensitive_access)])
async def files_read(request: FileReadRequest) -> dict[str, object]:
    try:
        return read_text_file(request.root, request.path)
    except LocalFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/files/summarize", dependencies=[Depends(require_sensitive_access)])
async def files_summarize(request: FileSummaryRequest) -> dict[str, object]:
    try:
        file_payload = read_text_file(request.root, request.path)
        content = str(file_payload["content"])
        prompt = f"""
{request.instruction}

Fichier: {file_payload['root']}/{file_payload['path']}

Contenu:
{content}
""".strip()
        summary = await ask_ollama([{"role": "user", "content": prompt}])
    except LocalFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "file": {
            "root": file_payload["root"],
            "path": file_payload["path"],
            "size": file_payload["size"],
            "truncated": file_payload["truncated"],
        },
        "summary": summary,
    }


@app.post("/web/search")
async def web_search(request: WebSearchRequest) -> dict[str, object]:
    try:
        results = await search_web(request.query, limit=request.limit)
    except WebSearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "query": request.query,
        "results": [
            {
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet,
            }
            for result in results
        ],
        "context": format_web_results(request.query, results),
    }


@app.post("/browser/open-tabs", dependencies=[Depends(require_sensitive_access)])
async def browser_open_tabs(request: BrowserOpenTabsRequest) -> dict[str, object]:
    opened: list[str] = []
    rejected: list[str] = []

    for url in request.urls:
        clean_url = url.strip()
        if not clean_url.startswith(("http://", "https://")):
            rejected.append(clean_url)
            continue

        open_url(clean_url)
        opened.append(clean_url)

    return {
        "opened": opened,
        "rejected": rejected,
    }


@app.post("/browser/assist", dependencies=[Depends(require_sensitive_access)])
async def browser_assist(request: BrowserAssistRequest) -> dict[str, object]:
    try:
        detected = detect_browser_assist(request.message)
        response = open_assisted_browser_from_message(request.message)
    except BrowserAssistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "opened": bool(response),
        "response": response,
        "detected": detected,
    }


@app.post("/stitch/design", dependencies=[Depends(require_sensitive_access)])
async def stitch_design(request: StitchDesignRequest) -> dict[str, object]:
    try:
        package = prepare_stitch_design(
            request=request.request,
            project_name=request.project_name,
            design_direction=request.design_direction,
            open_in_browser=request.open_in_browser,
        )
    except StitchDesignError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "detected": wants_stitch_design(request.request),
        "prompt": package.prompt,
        "opened_url": package.opened_url,
        "copied_to_clipboard": package.copied_to_clipboard,
        "response": format_stitch_design_response(package),
    }


@app.post("/stitch/prompt")
async def stitch_prompt(request: StitchDesignRequest) -> dict[str, object]:
    return {
        "detected": wants_stitch_design(request.request),
        "prompt": build_stitch_prompt(
            request=request.request,
            project_name=request.project_name,
            design_direction=request.design_direction,
        ),
    }


@app.post("/spotify/open", dependencies=[Depends(require_sensitive_access)])
async def spotify_open(request: SpotifyOpenRequest) -> dict[str, object]:
    try:
        detected = detect_spotify_request(request.message)
        response = open_spotify_from_message(request.message)
    except SpotifyAssistError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "opened": bool(response),
        "response": response,
        "detected": detected,
    }


@app.post("/beeper/open", dependencies=[Depends(require_sensitive_access)])
async def beeper_open() -> dict[str, object]:
    try:
        return open_beeper()
    except BeeperAssistantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/beeper/debrief", dependencies=[Depends(require_sensitive_access)])
async def beeper_debrief(request: BeeperRequest) -> dict[str, object]:
    try:
        response = await build_beeper_chat_response(request.message)
    except BeeperAssistantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "response": response,
        "reply_requested": wants_beeper_reply(request.message),
    }


@app.get("/desktop/status", dependencies=[Depends(require_sensitive_access)])
async def desktop_automation_status() -> dict[str, object]:
    return desktop_status()


@app.post("/desktop/click", dependencies=[Depends(require_sensitive_access)])
async def desktop_automation_click(request: DesktopClickRequest) -> dict[str, object]:
    try:
        result = click_pixel(request.x, request.y)
    except DesktopAutomationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "executed": result.executed,
        "message": result.message,
    }


@app.post("/desktop/click-ratio", dependencies=[Depends(require_sensitive_access)])
async def desktop_automation_click_ratio(request: DesktopClickRatioRequest) -> dict[str, object]:
    try:
        result = click_ratio(request.x_ratio, request.y_ratio)
    except DesktopAutomationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "executed": result.executed,
        "message": result.message,
    }


@app.post("/desktop/key", dependencies=[Depends(require_sensitive_access)])
async def desktop_automation_key(request: DesktopKeyRequest) -> dict[str, object]:
    try:
        result = press_key(request.key, presses=request.presses)
    except DesktopAutomationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "executed": result.executed,
        "message": result.message,
    }


@app.get("/screen/status", dependencies=[Depends(require_sensitive_access)])
async def screen_reader_status() -> dict[str, object]:
    return screen_status()


@app.get("/screen/latest", dependencies=[Depends(require_sensitive_access)])
async def screen_reader_latest() -> dict[str, object]:
    return {
        "latest": latest_screen_analysis(),
        "status": screen_status(),
    }


@app.post("/screen/watch/run-once", dependencies=[Depends(require_sensitive_access)])
async def screen_watch_run_once() -> dict[str, object]:
    try:
        return await run_screen_watch_once()
    except ScreenReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/screen/capture", dependencies=[Depends(require_sensitive_access)])
async def screen_reader_capture() -> dict[str, object]:
    try:
        return capture_screen()
    except ScreenReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/screen/analyze", dependencies=[Depends(require_sensitive_access)])
async def screen_reader_analyze(request: ScreenAnalyzeRequest) -> dict[str, object]:
    try:
        return await analyze_screen(
            instruction=request.instruction,
            auto_fix=request.auto_fix,
        )
    except ScreenReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/screen/act", dependencies=[Depends(require_sensitive_access)])
async def screen_visual_action(request: VisualActionRequest) -> dict[str, object]:
    try:
        return await analyze_visual_action(request.instruction, execute=request.execute)
    except VisualActionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/terminal/error/analyze", dependencies=[Depends(require_sensitive_access)])
async def terminal_error_analyze(request: TerminalErrorAnalyzeRequest) -> dict[str, object]:
    diagnosis = analyze_terminal_error(request.error)
    launched = None
    if request.auto_fix and diagnosis.fix and diagnosis.fix.safe_to_launch:
        try:
            launched = launch_terminal_fix(diagnosis.fix.key)
        except TerminalDoctorError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "diagnosis": diagnosis_to_dict(diagnosis),
        "launched": launched,
    }


@app.post("/terminal/error/fix", dependencies=[Depends(require_sensitive_access)])
async def terminal_error_fix(request: TerminalFixRequest) -> dict[str, object]:
    try:
        return launch_terminal_fix(request.fix_key)
    except TerminalDoctorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/gmail/messages", dependencies=[Depends(require_sensitive_access)])
async def gmail_messages(
    q: str = Query(default="in:inbox newer_than:14d", min_length=1, max_length=500),
    max_results: int = Query(default=10, ge=1, le=25),
) -> dict[str, object]:
    try:
        messages = list_gmail_messages(query=q, max_results=max_results)
    except GmailIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "query": q,
        "messages": [message_to_dict(message) for message in messages],
    }


@app.get("/gmail/messages/{message_id}", dependencies=[Depends(require_sensitive_access)])
async def gmail_message_detail(message_id: str) -> dict[str, object]:
    try:
        message = get_gmail_message(message_id)
    except GmailIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "message": message_to_dict(message, include_body=True),
    }


@app.get("/inbox/smart", dependencies=[Depends(require_sensitive_access)])
async def smart_inbox() -> dict[str, object]:
    return collect_inbox_signals()


@app.post("/gmail/reply-draft", dependencies=[Depends(require_sensitive_access)])
async def gmail_reply_draft(request: GmailReplyDraftRequest) -> dict[str, object]:
    try:
        message = get_gmail_message(request.message_id)
        examples = find_sent_examples(message.sender_email)
        prompt = f"""
Tu dois rediger un brouillon de reponse email pour Victor.
Ne dis jamais que le mail a ete envoye.
La reponse sera creee dans Gmail comme brouillon reel si possible, mais jamais envoyee automatiquement.
Tu reponds comme Victor, jamais comme l'expediteur.
Utilise uniquement le contenu du mail recu. N'invente pas de donnees absentes.

Instruction de Victor:
{request.instruction}

Mail recu:
{format_email_for_prompt(message)}

Exemples de mails deja envoyes par Victor:
{format_sent_examples_for_prompt(examples)}

Format obligatoire:
Objet: ...
Corps:
...
""".strip()
        draft = await ask_ollama([{"role": "user", "content": prompt}])
        subject, body = parse_reply_draft(draft, message.subject)
        gmail_draft = None
        if request.create_in_gmail:
            gmail_draft = create_gmail_reply_draft(
                message,
                body=body,
                subject=subject,
                open_in_browser=request.open_in_browser,
            )
    except GmailIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "sent": False,
        "created_in_gmail": bool(gmail_draft),
        "requires_confirmation_before_send": True,
        "source_message": message_to_dict(message),
        "sent_examples_used": len(examples),
        "subject": subject,
        "body": body,
        "draft": draft,
        "gmail_draft": gmail_draft,
    }


@app.post("/linkedin/post-draft", dependencies=[Depends(require_sensitive_access)])
async def linkedin_post_draft(request: LinkedInPostDraftRequest) -> dict[str, object]:
    try:
        draft = await draft_linkedin_post(
            topic=request.topic,
            angle=request.angle,
            audience=request.audience,
            format_name=request.format_name,
        )
    except LinkedInAssistantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "published": False,
        "requires_confirmation_before_publish": True,
        "draft": draft,
    }


@app.post("/linkedin/comment-draft", dependencies=[Depends(require_sensitive_access)])
async def linkedin_comment_draft(request: LinkedInCommentDraftRequest) -> dict[str, object]:
    try:
        draft = await draft_linkedin_comment(
            post_context=request.post_context,
            intent=request.intent,
        )
    except LinkedInAssistantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "published": False,
        "requires_confirmation_before_publish": True,
        "draft": draft,
    }


@app.post("/brief/morning", dependencies=[Depends(require_sensitive_access)])
async def morning_brief() -> dict[str, object]:
    try:
        brief = await generate_morning_brief()
    except RssBriefError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (BriefStoreError, OllamaClientError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "brief": brief_to_dict(brief),
    }


@app.post("/brief/smart", dependencies=[Depends(require_sensitive_access)])
async def smart_brief() -> dict[str, object]:
    try:
        payload = await generate_smart_brief_payload()
    except SmartBriefError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (BriefStoreError, OllamaClientError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "brief": payload["brief_dict"],
        "ranked_items": payload["ranked_items"],
        "inbox": payload["inbox"],
        "stats": payload["stats"],
    }


@app.post("/brief/daily-launch", dependencies=[Depends(require_sensitive_access)])
async def daily_launch_brief(request: DailyLaunchRequest) -> dict[str, object]:
    try:
        return await get_daily_launch_brief(force=request.force)
    except DailyLaunchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BriefStoreError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/brief/latest", dependencies=[Depends(require_sensitive_access)])
async def latest_brief() -> dict[str, object]:
    try:
        brief = get_latest_brief()
    except BriefStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "brief": brief_to_dict(brief) if brief else None,
    }


@app.get("/projects", dependencies=[Depends(require_sensitive_access)])
async def projects() -> dict[str, object]:
    try:
        return {"projects": load_projects()}
    except ProjectStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/project-factory/plan", dependencies=[Depends(require_sensitive_access)])
async def project_factory_plan(request: ProjectFactoryPlanRequest) -> dict[str, object]:
    try:
        plan = build_project_plan(
            idea=request.idea,
            project_name=request.project_name or None,
        )
    except ProjectFactoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "plan": plan,
        "executed": False,
        "requires_confirmation": True,
    }


@app.post("/project-factory/actions", dependencies=[Depends(require_sensitive_access)])
async def project_factory_actions(request: ProjectFactoryPlanRequest) -> dict[str, object]:
    try:
        bundle = create_project_factory_actions(
            idea=request.idea,
            project_name=request.project_name or None,
        )
        plan = bundle["plan"]
        actions = bundle["actions"]
        auto_status = project_factory_auto_status()
        auto_results = (
            auto_execute_project_factory_actions(actions)
            if auto_status["auto_execute"]
            else []
        )
    except (ProjectFactoryError, ActionStoreError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "plan": plan,
        "actions": [action_to_dict(action) for action in actions],
        "auto": auto_status,
        "auto_results": auto_results,
        "executed": bool(auto_results),
        "requires_confirmation": not bool(auto_results),
    }


@app.get("/project-factory/agent-events", dependencies=[Depends(require_sensitive_access)])
async def project_factory_agent_events(limit: int = Query(default=30, ge=1, le=200)) -> dict[str, object]:
    return {
        "events": list_project_factory_agent_events(limit=limit),
    }


@app.get("/projects/{project_name}/tree", dependencies=[Depends(require_sensitive_access)])
async def project_tree_route(project_name: str) -> dict[str, object]:
    try:
        return project_tree(project_name)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/{project_name}/files/read", dependencies=[Depends(require_sensitive_access)])
async def project_file_read(project_name: str, request: ProjectFileReadRequest) -> dict[str, object]:
    try:
        return read_project_file(project_name, request.path)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/{project_name}/cursor-prompt", dependencies=[Depends(require_sensitive_access)])
async def project_cursor_prompt(project_name: str, request: CursorPromptRequest) -> dict[str, object]:
    try:
        prompt = build_cursor_prompt(project_name, request.task)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "prompt": prompt,
    }


@app.post("/projects/{project_name}/branch-plan", dependencies=[Depends(require_sensitive_access)])
async def project_branch_plan(project_name: str, request: BranchPlanRequest) -> dict[str, object]:
    try:
        return build_branch_plan(project_name, request.branch_name)
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/projects/{project_name}/terminal-error", dependencies=[Depends(require_sensitive_access)])
async def project_terminal_error(project_name: str, request: TerminalErrorRequest) -> dict[str, object]:
    try:
        tree = project_tree(project_name, limit=80)
        file_list = "\n".join(f"- {item['path']}" for item in tree["items"][:80])
        prompt = f"""
Analyse cette erreur terminal pour le projet {project_name}.

Structure partielle du projet:
{file_list}

Erreur:
{request.error}

Donne:
1. cause probable;
2. fichiers a inspecter;
3. plan de correction;
4. commandes de verification a lancer manuellement.
""".strip()
        analysis = await ask_ollama([{"role": "user", "content": prompt}])
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "analysis": analysis,
    }


@app.get("/projects/{project_name}/tasks", dependencies=[Depends(require_sensitive_access)])
async def project_tasks(project_name: str) -> dict[str, object]:
    try:
        get_project = load_projects()
        if not any(project["name"].lower() == project_name.lower() for project in get_project):
            raise ProjectStoreError(f"Projet introuvable: {project_name}")
        tasks = list_tasks(project_name)
    except (ProjectStoreError, TaskStoreError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "tasks": [task_to_dict(task) for task in tasks],
    }


@app.post("/projects/{project_name}/tasks", dependencies=[Depends(require_sensitive_access)])
async def project_task_create(
    project_name: str,
    request: ProjectTaskCreateRequest,
) -> dict[str, object]:
    try:
        if not any(project["name"].lower() == project_name.lower() for project in load_projects()):
            raise ProjectStoreError(f"Projet introuvable: {project_name}")
        task = create_task(
            project=project_name,
            title=request.title,
            description=request.description,
            priority=request.priority,
        )
    except (ProjectStoreError, TaskStoreError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "task": task_to_dict(task),
    }


@app.delete("/projects/{project_name}/tasks/{task_id}", dependencies=[Depends(require_sensitive_access)])
async def project_task_delete(project_name: str, task_id: int) -> dict[str, object]:
    try:
        deleted = delete_task(task_id, project=project_name)
    except TaskStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Tache introuvable.")

    return {
        "deleted": True,
        "id": task_id,
    }


@app.post("/projects/{project_name}/readme-draft", dependencies=[Depends(require_sensitive_access)])
async def project_readme_draft(project_name: str, request: ProjectDraftRequest) -> dict[str, object]:
    try:
        tree = project_tree(project_name, limit=160)
        project = tree["project"]
        file_list = "\n".join(f"- {item['path']}" for item in tree["items"][:160])
        prompt = f"""
Prepare un brouillon de README pour ce projet.

Projet: {project['name']}
Description connue: {project.get('description', '')}
Instruction supplementaire: {request.instruction}

Structure:
{file_list}

Ne pretends pas avoir ecrit le fichier. Donne seulement un brouillon Markdown.
""".strip()
        draft = await ask_ollama([{"role": "user", "content": prompt}])
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "draft": draft,
    }


@app.post("/projects/{project_name}/pr-plan", dependencies=[Depends(require_sensitive_access)])
async def project_pr_plan(project_name: str, request: ProjectDraftRequest) -> dict[str, object]:
    try:
        tree = project_tree(project_name, limit=120)
        project = tree["project"]
        file_list = "\n".join(f"- {item['path']}" for item in tree["items"][:120])
        prompt = f"""
Prepare une proposition de PR pour ce projet, sans inventer de changements deja faits.

Projet: {project['name']}
Demande ou contexte: {request.instruction}

Structure partielle:
{file_list}

Donne:
1. titre de PR;
2. description;
3. checklist de verification;
4. risques;
5. fichiers probables a modifier.
""".strip()
        plan = await ask_ollama([{"role": "user", "content": prompt}])
    except ProjectStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "plan": plan,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(chat_request: ChatRequest, http_request: Request) -> ChatResponse:
    if not chat_request.messages:
        raise HTTPException(status_code=400, detail="Le message est vide.")

    safe_messages = [
        {"role": message.role, "content": message.content.strip()}
        for message in chat_request.messages
        if message.content.strip()
    ]

    if not safe_messages or safe_messages[-1]["role"] != "user":
        raise HTTPException(
            status_code=400,
            detail="La conversation doit se terminer par un message utilisateur.",
        )

    trusted_actions = is_request_trusted(http_request)
    try:
        result = await process_chat_messages(
            safe_messages,
            mode=chat_request.mode,
            trusted_actions=trusted_actions,
        )
    except ChatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        session = append_chat_exchange(
            chat_request.session_id.strip() or None,
            str(safe_messages[-1]["content"]),
            str(result["message"]["content"]),
            channel="web",
        )
    except ChatHistoryError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        record_operator_tick(
            str(safe_messages[-1]["content"]),
            str(result["message"]["content"]),
            channel="web",
            trusted_actions=trusted_actions,
            conversation_context=safe_messages[:-1],
        )
    except OperatorJournalError:
        pass

    return ChatResponse(
        message=Message(**result["message"]),
        saved_memory=result.get("saved_memory"),
        pending_action=result.get("pending_action"),
        session_id=session.id,
    )


@app.post("/understand", dependencies=[Depends(require_sensitive_access)])
async def understand(request: UnderstandRequest, http_request: Request) -> dict[str, object]:
    safe_context = [
        {"role": message.role, "content": message.content.strip()}
        for message in request.context
        if message.content.strip()
    ]
    trusted_actions = is_request_trusted(http_request)
    frame = build_understanding_frame(
        request.message.strip(),
        conversation_context=safe_context,
        trusted_actions=trusted_actions,
    )
    cognitive_context = build_cognitive_context(
        request.message.strip(),
        conversation_context=safe_context,
        frame=frame,
    )
    frame = attach_cognitive_context(frame, cognitive_context)
    frame = await refine_understanding_with_ollama(
        request.message.strip(),
        conversation_context=safe_context,
        base_frame=frame,
        trusted_actions=trusted_actions,
    )
    return understanding_to_dict(frame)


@app.get("/self-improve/status", dependencies=[Depends(require_sensitive_access)])
async def self_improve_status() -> dict[str, object]:
    return {
        "enabled": settings.eva_self_improve_enabled,
        "project_name": settings.eva_self_improve_project_name,
        "auto_cursor_agent": settings.eva_self_improve_auto_cursor_agent,
        "detects_examples": [
            "Eva, dorenavant...",
            "A partir de maintenant...",
            "Je veux que Eva...",
            "Corrige ton comportement...",
        ],
    }


@app.post("/self-improve", dependencies=[Depends(require_sensitive_access)])
async def self_improve(request: SelfImproveRequest, http_request: Request) -> dict[str, object]:
    trusted_actions = is_request_trusted(http_request)
    message = request.message.strip()
    try:
        result = execute_self_improvement_loop(
            message,
            source=request.source.strip() or "api",
            trusted_actions=trusted_actions,
            auto_launch_agent=request.auto_launch_agent,
        )
    except SelfImproveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        **result,
        "detected": detect_self_improvement_request(message),
        "response": format_self_improvement_response(result),
    }


@app.post("/self-improve/plan", dependencies=[Depends(require_sensitive_access)])
async def self_improve_plan(request: SelfImproveRequest) -> dict[str, object]:
    plan = build_self_improvement_plan(
        request.message.strip(),
        source=request.source.strip() or "api",
        auto_launch_agent=request.auto_launch_agent,
    )
    return {
        "detected": detect_self_improvement_request(request.message),
        "plan": self_improvement_plan_to_dict(plan),
    }


@app.get("/self-improve/log", dependencies=[Depends(require_sensitive_access)])
async def self_improve_log(limit: int = Query(default=30, ge=1, le=200)) -> dict[str, object]:
    return {
        "events": list_self_improvement_events(limit=limit),
    }

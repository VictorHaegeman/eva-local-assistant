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
    find_sent_examples,
    format_email_for_prompt,
    format_sent_examples_for_prompt,
    get_gmail_message,
    gmail_status,
    list_gmail_messages,
    message_to_dict,
)
from app.integrations.gmail_auth import GmailAuthLaunchError, start_gmail_oauth_flow
from app.integrations.inbox_smart import collect_inbox_signals
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
from app.memory.obsidian_store import (
    ObsidianMemoryError,
    ensure_obsidian_vault,
    mirror_memory_to_obsidian,
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
from app.projects.task_store import (
    TaskStoreError,
    create_task,
    delete_task,
    init_task_store,
    list_tasks,
    task_to_dict,
)
from app.security.action_policy import autonomy_policy_text, policy_levels, requires_confirmation
from app.security.api_auth import is_request_trusted, require_sensitive_access
from app.skills.registry import list_skills
from app.social.instagram_public import (
    InstagramPublicError,
    ensure_socials_file,
    fetch_instagram_public_snapshots,
    instagram_status,
)
from app.tools.registry import list_tools
from app.web.web_search import WebSearchError, format_web_results, search_web


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    messages: list[Message] = Field(default_factory=list, max_length=50)
    mode: AgentModeName = "chat"


class ChatResponse(BaseModel):
    message: Message
    saved_memory: dict[str, object] | None = None
    pending_action: dict[str, object] | None = None


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=600)
    category: str = Field(default="general", min_length=1, max_length=40)


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
    action_type: Literal["command", "read_file", "write_file", "delete_path", "codex_prompt"]
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


class DailyLaunchRequest(BaseModel):
    force: bool = False


class GmailReplyDraftRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=200)
    instruction: str = Field(
        default="Redige une reponse claire, directe et cordiale.",
        min_length=1,
        max_length=5000,
    )


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
init_brief_store()
init_task_store()
init_action_store()

telegram_task: asyncio.Task[None] | None = None
heartbeat_task: asyncio.Task[None] | None = None


@app.on_event("startup")
async def startup_event() -> None:
    global heartbeat_task, telegram_task
    telegram_task = start_telegram_background_task()
    heartbeat_task = start_heartbeat_background_task()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if telegram_task:
        telegram_task.cancel()
    if heartbeat_task:
        heartbeat_task.cancel()


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
async def gmail_connect() -> dict[str, object]:
    try:
        return start_gmail_oauth_flow()
    except GmailAuthLaunchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        "policy": autonomy_policy_text(),
        "levels": policy_levels(),
        "project_factory": project_factory_auto_status(),
        "safe_without_confirmation": [
            "lecture/analyse dans les dossiers configures",
            "recherche web gratuite",
            "lecture Gmail si OAuth local est configure",
            "brouillon LinkedIn sans publication",
            "heartbeat local si active",
            "brouillon de reponse email sans envoi",
            "resume",
            "creation de taches locales",
            "preparation de prompts Cursor/Codex",
        ],
        "requires_confirmation": [
            "commande systeme hors Project Factory auto configuree",
            "modification ou suppression de fichier hors workspace Project Factory",
            "git push",
            "publication",
            "envoi de message",
            "envoi d'email",
            "publication LinkedIn",
            "compte externe",
        ],
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
        if not requires_confirmation(request.action_type, request.payload):
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
            description="Commande locale creee depuis l'API. Validation obligatoire.",
            payload=payload,
        )
    except ActionStoreError as exc:
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
La reponse doit etre prete a relire, modifier et valider par Victor.

Instruction de Victor:
{request.instruction}

Mail recu:
{format_email_for_prompt(message)}

Exemples de mails deja envoyes par Victor:
{format_sent_examples_for_prompt(examples)}

Donne uniquement:
1. Objet propose;
2. Brouillon du mail;
3. Points a verifier avant envoi.
""".strip()
        draft = await ask_ollama([{"role": "user", "content": prompt}])
    except GmailIntegrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaClientError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "sent": False,
        "requires_confirmation_before_send": True,
        "source_message": message_to_dict(message),
        "sent_examples_used": len(examples),
        "draft": draft,
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

    try:
        result = await process_chat_messages(
            safe_messages,
            mode=chat_request.mode,
            trusted_actions=is_request_trusted(http_request),
        )
    except ChatServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        message=Message(**result["message"]),
        saved_memory=result.get("saved_memory"),
        pending_action=result.get("pending_action"),
    )

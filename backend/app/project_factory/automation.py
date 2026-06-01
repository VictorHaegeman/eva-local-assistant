from app.actions.action_store import EvaAction, action_to_dict, update_action_status
from app.actions.executor import execute_action
from app.config import settings
from app.security.action_policy import can_auto_execute


AUTO_ACTION_ORDER = {
    "project_workspace_create": 10,
    "project_local_code_v1": 15,
    "clipboard_set_prompt": 20,
    "cursor_open_project": 30,
    "git_initial_commit": 40,
    "github_repo_create": 50,
    "cursor_agent_project_run": 60,
    "git_push": 90,
}


def _auto_enabled_for(action: EvaAction) -> tuple[bool, str]:
    if not (settings.eva_project_factory_auto_execute or settings.eva_auto_execute_actions):
        return False, "auto_execute desactive"

    if action.action_type == "clipboard_set_prompt":
        return settings.eva_project_factory_auto_copy_prompt, "auto_copy_prompt desactive"

    if action.action_type == "project_local_code_v1":
        return True, "local_v1 toujours actif dans Project Factory"

    if action.action_type == "cursor_open_project":
        return settings.eva_project_factory_auto_open_cursor, "auto_open_cursor desactive"

    if action.action_type == "git_initial_commit":
        return settings.eva_project_factory_auto_commit, "auto_commit desactive"

    if action.action_type == "github_repo_create":
        return settings.eva_project_factory_auto_github, "auto_github desactive"

    if action.action_type == "cursor_agent_project_run":
        return settings.eva_project_factory_auto_cursor_agent, "auto_cursor_agent desactive"

    if action.action_type == "git_push":
        return settings.eva_project_factory_auto_push, "auto_push desactive"

    allowed, reason = can_auto_execute(action.action_type, action.payload)
    return allowed, reason


def auto_execute_project_factory_actions(actions: list[EvaAction]) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    ordered_actions = sorted(actions, key=lambda action: AUTO_ACTION_ORDER.get(action.action_type, 999))
    has_agent_run = any(action.action_type == "cursor_agent_project_run" for action in actions)
    deferred_pushes: list[EvaAction] = []
    agent_started = False

    for action in ordered_actions:
        if action.action_type == "git_push" and has_agent_run:
            deferred_pushes.append(action)
            continue

        enabled, reason = _auto_enabled_for(action)
        if not enabled:
            results.append(
                {
                    "executed": False,
                    "skipped": True,
                    "reason": reason,
                    "action": action_to_dict(action),
                }
            )
            continue

        update_action_status(action.id, "approved")
        result = execute_action(action.id)
        results.append(result)
        if action.action_type == "cursor_agent_project_run":
            action_payload = result.get("action")
            if isinstance(action_payload, dict):
                agent_started = "started=True" in str(action_payload.get("result", ""))

    for action in deferred_pushes:
        if agent_started:
            results.append(
                {
                    "executed": False,
                    "skipped": True,
                    "reason": (
                        "push gere par le superviseur cursor-agent apres audit final"
                    ),
                    "action": action_to_dict(action),
                }
            )
            continue

        enabled, reason = _auto_enabled_for(action)
        if not enabled:
            results.append(
                {
                    "executed": False,
                    "skipped": True,
                    "reason": reason,
                    "action": action_to_dict(action),
                }
            )
            continue

        update_action_status(action.id, "approved")
        results.append(execute_action(action.id))

    return results


def project_factory_auto_status() -> dict[str, object]:
    return {
        "auto_execute": settings.eva_project_factory_auto_execute,
        "auto_copy_prompt": settings.eva_project_factory_auto_copy_prompt,
        "auto_open_cursor": settings.eva_project_factory_auto_open_cursor,
        "auto_local_v1": True,
        "auto_commit": settings.eva_project_factory_auto_commit,
        "auto_github": settings.eva_project_factory_auto_github,
        "auto_push": settings.eva_project_factory_auto_push,
        "auto_cursor_agent": settings.eva_project_factory_auto_cursor_agent,
        "agent_repair_once": settings.eva_project_factory_agent_repair_once,
        "agent_auto_commit": settings.eva_project_factory_agent_auto_commit,
    }


def format_project_factory_results(
    plan: dict[str, object],
    results: list[dict[str, object]],
) -> str:
    executed_lines: list[str] = []
    pending_lines: list[str] = []
    failed_lines: list[str] = []

    for result in results:
        action = result.get("action")
        if not isinstance(action, dict):
            continue

        action_id = action.get("id")
        action_type = action.get("action_type")
        title = action.get("title")
        status = action.get("status")

        result_text = str(action.get("result", ""))

        if result.get("executed") and "started=False" in result_text:
            pending_lines.append(f"- #{action_id} [{action_type}] {title}: {result_text}")
        elif result.get("executed"):
            executed_lines.append(f"- #{action_id} [{action_type}] {title}")
        elif status == "failed":
            failed_lines.append(f"- #{action_id} [{action_type}] {title}: {result_text}")
        else:
            reason = result.get("reason", "non execute")
            pending_lines.append(f"- #{action_id} [{action_type}] {title} ({reason})")

    lines = [
        f"Project Factory autonome lance pour {plan['project_name']}.",
        f"Dossier cible: {plan['workspace_path']}",
        f"Repo GitHub propose: {plan['repo_name']}",
        "",
    ]

    if executed_lines:
        lines.append("Execute automatiquement:")
        lines.extend(executed_lines)
        lines.append("")

    if pending_lines:
        lines.append("Non lance ou differe:")
        lines.extend(pending_lines)
        lines.append("")

    if failed_lines:
        lines.append("A verifier:")
        lines.extend(failed_lines)
        lines.append("")

    lines.append("Eva n'a pas envoye de message externe et n'a pas appele d'API OpenAI.")
    return "\n".join(lines).strip()

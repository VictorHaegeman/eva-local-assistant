from dataclasses import dataclass
from typing import Any, Literal

from app.config import settings


ActionPolicyLevel = Literal["read_only", "draft_only", "confirmation_required", "blocked"]


@dataclass(frozen=True)
class ActionPolicyDecision:
    level: ActionPolicyLevel
    reason: str


READ_ONLY_ACTIONS = {
    "read_file",
    "project_context",
    "web_search",
    "gmail_read",
    "heartbeat_status",
    "doctor_check",
}

DRAFT_ONLY_ACTIONS = {
    "codex_prompt",
    "project_prompt",
    "project_factory_plan",
    "gmail_reply_draft",
    "linkedin_draft",
    "linkedin_browser_prepare_post",
    "readme_draft",
    "pr_plan",
}

CONFIRMATION_REQUIRED_ACTIONS = {
    "command",
    "delete_path",
    "send_message",
    "send_email",
    "write_file",
    "project_workspace_create",
    "clipboard_set_prompt",
    "cursor_open_project",
    "git_initial_commit",
    "github_repo_create",
    "git_push",
    "publish_content",
}

BLOCKED_ACTIONS = {
    "store_secret",
    "openai_api_call",
    "paid_cloud_call",
    "permanent_delete_mail",
}

CRITICAL_COMMAND_MARKERS = (
    "git push",
    "git reset",
    "git clean",
    "git checkout --",
    "gh pr create",
    "gh pr merge",
    "gh repo delete",
    "remove-item",
    "rm ",
    "del ",
    "erase ",
    "rmdir",
    "rd ",
    "shutdown",
    "restart-computer",
    "format",
    "publish",
    "invoke-expression",
    "iex ",
    " -enc",
    "set-executionpolicy",
)

OPERATOR_AUTO_ACTIONS = {
    "read_file",
    "project_context",
    "web_search",
    "gmail_read",
    "heartbeat_status",
    "doctor_check",
    "codex_prompt",
    "project_prompt",
    "project_factory_plan",
    "gmail_reply_draft",
    "linkedin_draft",
    "linkedin_browser_prepare_post",
    "readme_draft",
    "pr_plan",
    "write_file",
    "project_workspace_create",
    "clipboard_set_prompt",
    "cursor_open_project",
    "git_initial_commit",
    "github_repo_create",
}

ALWAYS_PROTECTED_ACTIONS = {
    "send_message",
    "send_email",
    "publish_content",
    "permanent_delete_mail",
}


def classify_action(action_type: str, payload: dict[str, Any] | None = None) -> ActionPolicyDecision:
    clean_type = action_type.strip().lower()
    payload = payload or {}

    if clean_type in BLOCKED_ACTIONS:
        return ActionPolicyDecision("blocked", "Action bloquee par la politique locale Eva.")

    if clean_type in READ_ONLY_ACTIONS:
        return ActionPolicyDecision("read_only", "Lecture ou diagnostic sans modification.")

    if clean_type in DRAFT_ONLY_ACTIONS:
        return ActionPolicyDecision("draft_only", "Brouillon ou preparation sans action externe.")

    if clean_type in CONFIRMATION_REQUIRED_ACTIONS:
        return ActionPolicyDecision("confirmation_required", "Action critique avec validation obligatoire.")

    command = str(payload.get("command", "")).strip().lower()
    if command and any(marker in command for marker in CRITICAL_COMMAND_MARKERS):
        return ActionPolicyDecision("confirmation_required", "Commande critique detectee.")

    return ActionPolicyDecision(
        "confirmation_required",
        "Type d'action inconnu: validation obligatoire par defaut.",
    )


def requires_confirmation(action_type: str, payload: dict[str, Any] | None = None) -> bool:
    return classify_action(action_type, payload).level == "confirmation_required"


def is_blocked(action_type: str, payload: dict[str, Any] | None = None) -> bool:
    return classify_action(action_type, payload).level == "blocked"


def command_is_critical(command: str) -> bool:
    clean_command = command.strip().lower()
    return bool(clean_command and any(marker in clean_command for marker in CRITICAL_COMMAND_MARKERS))


def can_auto_execute(action_type: str, payload: dict[str, Any] | None = None) -> tuple[bool, str]:
    payload = payload or {}
    clean_type = action_type.strip().lower()

    if is_blocked(clean_type, payload):
        return False, "action bloquee"

    if settings.eva_autonomy_mode.strip().lower() not in {"operator", "autonomous", "auto"}:
        return False, "mode autonomie non operator"

    if not settings.eva_auto_execute_actions:
        return False, "auto-execution desactivee"

    if clean_type in ALWAYS_PROTECTED_ACTIONS and not settings.eva_allow_auto_external_send:
        return False, "envoi/publication externe protegee"

    if clean_type == "delete_path":
        return (
            settings.eva_allow_auto_delete,
            "suppression auto desactivee" if not settings.eva_allow_auto_delete else "suppression auto autorisee",
        )

    if clean_type == "git_push":
        git_push_allowed = settings.eva_allow_auto_git_push or settings.eva_project_factory_auto_push
        return (
            git_push_allowed,
            "git push auto desactive" if not git_push_allowed else "git push auto autorise",
        )

    if clean_type == "command":
        command = str(payload.get("command", ""))
        if not settings.eva_auto_execute_commands:
            return False, "commandes auto desactivees"
        if command_is_critical(command):
            return False, "commande critique protegee"
        return True, "commande locale non critique"

    if clean_type == "write_file" and not settings.eva_auto_write_files:
        return False, "ecriture fichier auto desactivee"

    if clean_type == "github_repo_create" and not settings.eva_project_factory_auto_github:
        return False, "creation repo GitHub auto desactivee"

    if clean_type in OPERATOR_AUTO_ACTIONS:
        return True, "mode operator"

    decision = classify_action(clean_type, payload)
    if decision.level in {"read_only", "draft_only"}:
        return True, decision.reason

    return False, "action non reconnue comme auto-executable"


def autonomy_policy_text() -> str:
    return (
        "Politique d'autonomie Eva:\n"
        f"- mode actuel: {settings.eva_autonomy_mode}.\n"
        "- read_only: Eva peut lire, diagnostiquer et rechercher sans modifier.\n"
        "- draft_only: Eva peut preparer un brouillon, un prompt ou un plan sans l'envoyer.\n"
        "- operator: Eva execute automatiquement les actions locales non critiques depuis le PC ou Telegram autorise.\n"
        "- protege: suppression, publication, envoi externe et commandes critiques restent bloques "
        "sauf variable explicite.\n"
        "- blocked: Eva refuse les secrets, appels OpenAI/API payante obligatoires et suppressions "
        "irreversibles non encadrees."
    )


def policy_levels() -> list[dict[str, str]]:
    return [
        {
            "level": "read_only",
            "description": "Lecture, recherche, diagnostic, aucune modification.",
        },
        {
            "level": "draft_only",
            "description": "Brouillon de mail, prompt Cursor, plan de PR, rien n'est envoye.",
        },
        {
            "level": "confirmation_required",
            "description": "Action sensible demandant une validation humaine.",
        },
        {
            "level": "blocked",
            "description": "Action refusee par la politique locale.",
        },
    ]

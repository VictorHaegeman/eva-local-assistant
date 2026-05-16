from dataclasses import dataclass
from typing import Any, Literal


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
    "remove-item",
    "del ",
    "erase ",
    "rmdir",
    "rd ",
    "shutdown",
    "format",
    "publish",
)


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


def autonomy_policy_text() -> str:
    return (
        "Politique d'autonomie Eva:\n"
        "- read_only: Eva peut lire, diagnostiquer et rechercher sans modifier.\n"
        "- draft_only: Eva peut preparer un brouillon, un prompt ou un plan sans l'envoyer.\n"
        "- confirmation_required: Eva doit demander validation avant commande, ecriture, suppression, "
        "git push, publication ou envoi externe.\n"
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

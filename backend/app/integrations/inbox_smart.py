from typing import Any

from app.integrations.gmail_client import (
    GmailIntegrationError,
    get_gmail_message,
    gmail_status,
    list_gmail_messages,
    message_to_dict,
)


MAX_BODY_CHARS = 4000


def _message_preview(message: Any, include_body: bool = False) -> dict[str, Any]:
    payload = message_to_dict(message, include_body=include_body)
    if include_body and payload.get("body"):
        payload["body"] = payload["body"][:MAX_BODY_CHARS]
    return payload


def _gmail_ready() -> bool:
    status = gmail_status()
    return bool(status["enabled"] and status["credentials_exists"] and status["token_exists"])


def collect_inbox_signals(
    max_inbox: int = 8,
    max_linkedin: int = 5,
    include_bodies: bool = True,
) -> dict[str, Any]:
    status = gmail_status()
    if not _gmail_ready():
        return {
            "enabled": status["enabled"],
            "available": False,
            "status": status,
            "messages": [],
            "noise_messages": [],
            "linkedin_notifications": [],
            "summary": "Gmail n'est pas encore connecte. Le Smart Brief utilisera seulement les sources RSS/web.",
        }

    try:
        inbox_refs = list_gmail_messages(
            query="in:inbox newer_than:7d",
            max_results=min(max_inbox * 2, 25),
        )
        linkedin_refs = list_gmail_messages(
            query='in:inbox newer_than:14d ("LinkedIn" OR "linkedin")',
            max_results=max_linkedin,
        )

        messages = []
        noise_messages = []
        for message in inbox_refs:
            full_message = get_gmail_message(message.id) if include_bodies else message
            preview = _message_preview(full_message, include_body=include_bodies)
            if preview.get("is_noise"):
                noise_messages.append(preview)
            else:
                messages.append(preview)

        messages = sorted(
            messages,
            key=lambda item: int(item.get("importance_score", 0)),
            reverse=True,
        )[:max_inbox]

        linkedin_notifications = []
        for message in linkedin_refs:
            full_message = get_gmail_message(message.id) if include_bodies else message
            linkedin_notifications.append(_message_preview(full_message, include_body=include_bodies))
    except GmailIntegrationError as exc:
        return {
            "enabled": status["enabled"],
            "available": False,
            "status": status,
            "messages": [],
            "noise_messages": [],
            "linkedin_notifications": [],
            "summary": f"Gmail indisponible pour le Smart Brief: {exc}",
        }

    return {
        "enabled": True,
        "available": True,
        "status": status,
        "messages": messages,
        "noise_messages": noise_messages,
        "linkedin_notifications": linkedin_notifications,
        "summary": (
            f"{len(messages)} mails utiles lus, {len(noise_messages)} pubs/newsletters mises de cote, "
            f"{len(linkedin_notifications)} signaux LinkedIn detectes via Gmail."
        ),
    }


def format_inbox_signals_for_prompt(signals: dict[str, Any]) -> str:
    if not signals.get("available"):
        return str(signals.get("summary", "Gmail non disponible."))

    lines = [str(signals.get("summary", "Inbox lue en lecture seule."))]

    messages = signals.get("messages", [])
    if messages:
        lines.append("\nMails recents:")
        for index, message in enumerate(messages[:8], start=1):
            lines.append(
                f"{index}. {message.get('subject', '(sans objet)')}\n"
                f"De: {message.get('from', '')}\n"
                f"Date: {message.get('date', '')}\n"
                f"Tri: {message.get('importance_category', 'normal')} "
                f"({message.get('importance_score', 0)}/100) - {message.get('classification_reason', '')}\n"
                f"Extrait: {(message.get('body') or message.get('snippet') or '')[:1200]}"
            )

    noise_messages = signals.get("noise_messages", [])
    if noise_messages:
        lines.append("\nPubs/newsletters mises de cote:")
        for index, message in enumerate(noise_messages[:5], start=1):
            lines.append(
                f"{index}. {message.get('subject', '(sans objet)')} - "
                f"{message.get('from', '')} - "
                f"{message.get('importance_category', 'pub')} "
                f"({message.get('importance_score', 0)}/100)"
            )

    linkedin_notifications = signals.get("linkedin_notifications", [])
    if linkedin_notifications:
        lines.append("\nNotifications LinkedIn detectees via Gmail:")
        for index, message in enumerate(linkedin_notifications[:5], start=1):
            lines.append(
                f"{index}. {message.get('subject', '(sans objet)')}\n"
                f"De: {message.get('from', '')}\n"
                f"Date: {message.get('date', '')}\n"
                f"Extrait: {(message.get('body') or message.get('snippet') or '')[:1200]}"
            )

    return "\n\n".join(lines)

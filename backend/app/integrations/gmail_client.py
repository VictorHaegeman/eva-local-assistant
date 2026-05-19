import base64
import re
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from app.config import settings


class GmailIntegrationError(Exception):
    """Raised when Eva cannot use Gmail safely."""


@dataclass(frozen=True)
class GmailMessage:
    id: str
    thread_id: str
    sender: str
    sender_email: str
    reply_to: str
    reply_to_email: str
    to: str
    subject: str
    date: str
    snippet: str
    body: str = ""
    message_id_header: str = ""
    references: str = ""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
CALENDAR_READONLY_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GMAIL_SCOPES = [
    GMAIL_READONLY_SCOPE,
    GMAIL_COMPOSE_SCOPE,
    CALENDAR_READONLY_SCOPE,
]


def _resolve_local_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def gmail_credentials_path() -> Path:
    return _resolve_local_path(settings.eva_gmail_credentials_path)


def gmail_token_path() -> Path:
    return _resolve_local_path(settings.eva_gmail_token_path)


def gmail_status() -> dict[str, object]:
    token_scope_status = google_token_scope_status()
    compose_status = google_token_scope_status([GMAIL_COMPOSE_SCOPE])
    return {
        "enabled": settings.eva_gmail_enabled,
        "credentials_path": str(gmail_credentials_path()),
        "credentials_exists": gmail_credentials_path().exists(),
        "token_path": str(gmail_token_path()),
        "token_exists": gmail_token_path().exists(),
        "token_has_required_scopes": token_scope_status["has_required_scopes"],
        "missing_scopes": token_scope_status["missing_scopes"],
        "scopes": GMAIL_SCOPES,
        "can_create_drafts": compose_status["has_required_scopes"],
        "drafts_require_manual_send": True,
        "can_send": False,
        "send_requires_confirmation": True,
    }


def google_token_scope_status(required_scopes: list[str] | None = None) -> dict[str, object]:
    scopes_to_check = required_scopes or GMAIL_SCOPES
    token_file = gmail_token_path()
    if not token_file.exists():
        return {
            "has_required_scopes": False,
            "missing_scopes": scopes_to_check,
        }

    try:
        import json

        payload = json.loads(token_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "has_required_scopes": False,
            "missing_scopes": scopes_to_check,
        }

    raw_scopes = payload.get("scopes") or payload.get("scope") or []
    if isinstance(raw_scopes, str):
        scopes = set(raw_scopes.split())
    elif isinstance(raw_scopes, list):
        scopes = {str(scope) for scope in raw_scopes}
    else:
        scopes = set()

    missing = [scope for scope in scopes_to_check if scope not in scopes]
    return {
        "has_required_scopes": not missing,
        "missing_scopes": missing,
    }


def _require_token_scopes(required_scopes: list[str]) -> None:
    status = google_token_scope_status(required_scopes)
    if status["has_required_scopes"]:
        return

    missing = ", ".join(str(scope) for scope in status["missing_scopes"])
    raise GmailIntegrationError(
        "Token Google incomplet pour cette action. "
        "Reconnecte Google depuis le panneau Gmail avec 'Reconnecter scopes'. "
        f"Scopes manquants: {missing}"
    )


def _google_imports() -> tuple[Any, Any, Any]:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailIntegrationError(
            "Dependances Gmail absentes. Lance: pip install -r backend/requirements.txt"
        ) from exc

    return Request, Credentials, build


def _gmail_service() -> Any:
    if not settings.eva_gmail_enabled:
        raise GmailIntegrationError("Gmail est desactive. Active EVA_GMAIL_ENABLED=true.")

    credentials_file = gmail_credentials_path()
    token_file = gmail_token_path()
    if not credentials_file.exists():
        raise GmailIntegrationError(
            "Fichier OAuth Gmail absent. Place-le dans data/gmail_credentials.json."
        )
    if not token_file.exists():
        raise GmailIntegrationError(
            "Token Gmail absent. Lance: cd backend puis python -m app.integrations.gmail_auth"
        )

    Request, Credentials, build = _google_imports()
    credentials = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_file.write_text(credentials.to_json(), encoding="utf-8")

    if not credentials.valid:
        raise GmailIntegrationError(
            "Token Gmail invalide. Relance: cd backend puis python -m app.integrations.gmail_auth"
        )

    return build("gmail", "v1", credentials=credentials)


def _header(headers: list[dict[str, str]], name: str) -> str:
    for header in headers:
        if header.get("name", "").lower() == name.lower():
            return str(header.get("value", "")).strip()
    return ""


def _decode_body(data: str) -> str:
    if not data:
        return ""
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _body_from_payload(payload: dict[str, Any]) -> str:
    mime_type = str(payload.get("mimeType", ""))
    body = payload.get("body", {})
    if mime_type.startswith("text/plain") and isinstance(body, dict):
        decoded = _decode_body(str(body.get("data", ""))).strip()
        if decoded:
            return decoded

    parts = payload.get("parts", [])
    if isinstance(parts, list):
        plain_parts = []
        html_fallback = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_mime = str(part.get("mimeType", ""))
            part_body = part.get("body", {})
            nested = _body_from_payload(part)
            if part_mime.startswith("text/plain") and nested:
                plain_parts.append(nested)
            elif part_mime.startswith("text/html") and isinstance(part_body, dict):
                html = _decode_body(str(part_body.get("data", ""))).strip()
                if html:
                    html_fallback.append(_html_to_text(html))
            elif nested:
                plain_parts.append(nested)

        if plain_parts:
            return "\n\n".join(plain_parts).strip()
        if html_fallback:
            return "\n\n".join(html_fallback).strip()

    return ""


def _html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<.*?>", " ", text)
    return " ".join(text.split())


def _message_from_payload(payload: dict[str, Any], include_body: bool) -> GmailMessage:
    headers = payload.get("payload", {}).get("headers", [])
    if not isinstance(headers, list):
        headers = []

    sender = _header(headers, "From")
    _, sender_email = parseaddr(sender)
    reply_to = _header(headers, "Reply-To")
    _, reply_to_email = parseaddr(reply_to)

    body = ""
    if include_body:
        body = _body_from_payload(payload.get("payload", {}))

    return GmailMessage(
        id=str(payload.get("id", "")),
        thread_id=str(payload.get("threadId", "")),
        sender=sender,
        sender_email=sender_email,
        reply_to=reply_to,
        reply_to_email=reply_to_email,
        to=_header(headers, "To"),
        subject=_header(headers, "Subject") or "(sans objet)",
        date=_header(headers, "Date"),
        snippet=str(payload.get("snippet", "")),
        body=body,
        message_id_header=_header(headers, "Message-ID"),
        references=_header(headers, "References"),
    )


def message_to_dict(message: GmailMessage, include_body: bool = False) -> dict[str, str]:
    payload = {
        "id": message.id,
        "thread_id": message.thread_id,
        "from": message.sender,
        "from_email": message.sender_email,
        "reply_to": message.reply_to,
        "reply_to_email": message.reply_to_email,
        "to": message.to,
        "subject": message.subject,
        "date": message.date,
        "snippet": message.snippet,
    }
    if include_body:
        payload["body"] = message.body
    return payload


def list_gmail_messages(query: str = "in:inbox newer_than:14d", max_results: int = 10) -> list[GmailMessage]:
    service = _gmail_service()
    safe_limit = min(max(max_results, 1), 25)

    response = (
        service.users()
        .messages()
        .list(userId="me", q=query, maxResults=safe_limit)
        .execute()
    )
    message_refs = response.get("messages", [])
    if not isinstance(message_refs, list):
        return []

    messages = []
    for message_ref in message_refs:
        message_id = str(message_ref.get("id", ""))
        if not message_id:
            continue
        message_payload = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="metadata")
            .execute()
        )
        messages.append(_message_from_payload(message_payload, include_body=False))

    return messages


def get_gmail_message(message_id: str) -> GmailMessage:
    clean_id = message_id.strip()
    if not clean_id:
        raise GmailIntegrationError("ID Gmail vide.")

    service = _gmail_service()
    payload = (
        service.users()
        .messages()
        .get(userId="me", id=clean_id, format="full")
        .execute()
    )
    return _message_from_payload(payload, include_body=True)


def _reply_subject(subject: str) -> str:
    clean_subject = (subject or "(sans objet)").strip()
    if clean_subject.lower().startswith("re:"):
        return clean_subject
    return f"Re: {clean_subject}"


def _encode_raw_message(message: EmailMessage) -> str:
    return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")


def create_gmail_reply_draft(
    original: GmailMessage,
    body: str,
    subject: str = "",
    open_in_browser: bool = False,
) -> dict[str, str]:
    clean_body = body.strip()
    if not clean_body:
        raise GmailIntegrationError("Brouillon vide: Eva refuse de creer un draft Gmail vide.")

    _require_token_scopes([GMAIL_COMPOSE_SCOPE])
    service = _gmail_service()

    recipient = original.reply_to_email or original.sender_email
    if not recipient:
        raise GmailIntegrationError("Impossible de creer le brouillon: destinataire introuvable.")

    profile = service.users().getProfile(userId="me").execute()
    from_email = str(profile.get("emailAddress", "")).strip()

    email = EmailMessage()
    if from_email:
        email["From"] = from_email
    email["To"] = recipient
    email["Subject"] = subject.strip() or _reply_subject(original.subject)
    if original.message_id_header:
        email["In-Reply-To"] = original.message_id_header
        references = " ".join(
            part for part in (original.references, original.message_id_header) if part
        )
        if references:
            email["References"] = references
    email.set_content(clean_body)

    request_body: dict[str, object] = {
        "message": {
            "raw": _encode_raw_message(email),
            "threadId": original.thread_id,
        }
    }
    draft = service.users().drafts().create(userId="me", body=request_body).execute()
    draft_id = str(draft.get("id", ""))
    draft_message = draft.get("message", {})
    draft_message_id = str(draft_message.get("id", "")) if isinstance(draft_message, dict) else ""
    thread_id = str(draft_message.get("threadId", original.thread_id)) if isinstance(draft_message, dict) else original.thread_id
    thread_url = f"https://mail.google.com/mail/u/0/#all/{thread_id or original.thread_id}"
    drafts_url = "https://mail.google.com/mail/u/0/#drafts"

    if open_in_browser:
        from app.integrations.browser import open_url

        open_url(thread_url)

    return {
        "created": "true",
        "sent": "false",
        "draft_id": draft_id,
        "draft_message_id": draft_message_id,
        "thread_id": thread_id,
        "thread_url": thread_url,
        "drafts_url": drafts_url,
        "to": recipient,
        "subject": str(email["Subject"]),
    }


def find_sent_examples(recipient_email: str = "", max_results: int | None = None) -> list[GmailMessage]:
    safe_limit = max_results or settings.eva_gmail_max_sent_examples
    safe_limit = min(max(safe_limit, 1), 10)

    query = "in:sent newer_than:365d"
    if recipient_email:
        query = f"{query} to:{recipient_email}"

    refs = list_gmail_messages(query=query, max_results=safe_limit)
    examples = []
    for message in refs:
        examples.append(get_gmail_message(message.id))
    return examples


def format_email_for_prompt(message: GmailMessage) -> str:
    return (
        f"De: {message.sender}\n"
        f"A: {message.to}\n"
        f"Date: {message.date}\n"
        f"Objet: {message.subject}\n\n"
        f"{message.body or message.snippet}"
    ).strip()


def format_sent_examples_for_prompt(examples: list[GmailMessage]) -> str:
    if not examples:
        return "Aucun exemple envoye pertinent trouve."

    blocks = []
    for index, message in enumerate(examples, start=1):
        body = (message.body or message.snippet)[:4000]
        blocks.append(
            f"Exemple {index}\n"
            f"Objet: {message.subject}\n"
            f"Date: {message.date}\n\n"
            f"{body}"
        )

    return "\n\n---\n\n".join(blocks)

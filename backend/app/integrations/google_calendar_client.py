from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.integrations.gmail_client import (
    GMAIL_SCOPES,
    GOOGLE_REAUTH_ERROR,
    GmailIntegrationError,
    _google_imports,
    gmail_credentials_path,
    gmail_token_path,
    google_token_scope_status,
    is_google_reauth_error,
    quarantine_gmail_token,
)


CALENDAR_API_ENABLE_URL = (
    "https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview"
)


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    summary: str
    start: str
    end: str
    location: str
    html_link: str


def calendar_status() -> dict[str, object]:
    token_status = google_token_scope_status()
    return {
        "enabled": True,
        "credentials_path": str(gmail_credentials_path()),
        "credentials_exists": gmail_credentials_path().exists(),
        "token_path": str(gmail_token_path()),
        "token_exists": gmail_token_path().exists(),
        "token_has_required_scopes": token_status["has_required_scopes"],
        "missing_scopes": token_status["missing_scopes"],
        "scopes": GMAIL_SCOPES,
        "can_write": False,
        "write_requires_confirmation": True,
    }


def _calendar_service() -> Any:
    credentials_file = gmail_credentials_path()
    token_file = gmail_token_path()
    token_status = google_token_scope_status()

    if not credentials_file.exists():
        raise GmailIntegrationError(
            "Fichier OAuth Google absent. Place-le dans data/gmail_credentials.json."
        )
    if not token_file.exists():
        raise GmailIntegrationError(
            "Token Google absent. Lance la connexion Google depuis le panneau Gmail."
        )
    if not token_status["has_required_scopes"]:
        raise GmailIntegrationError(
            "Token Google incomplet. Reconnecte Google avec les scopes Gmail + Calendar."
        )

    Request, Credentials, build = _google_imports()
    credentials = Credentials.from_authorized_user_file(str(token_file), GMAIL_SCOPES)

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
            token_file.write_text(credentials.to_json(), encoding="utf-8")
        except Exception as exc:
            if is_google_reauth_error(exc):
                quarantine_gmail_token(str(exc))
                raise GmailIntegrationError(GOOGLE_REAUTH_ERROR) from exc
            raise GmailIntegrationError(f"Impossible de rafraichir le token Google: {exc}") from exc

    if not credentials.valid:
        quarantine_gmail_token("credentials.valid=false")
        raise GmailIntegrationError("Token Google invalide. Relance la connexion Google.")

    return build("calendar", "v3", credentials=credentials)


def list_calendar_events(days: int = 7, max_results: int = 10) -> list[CalendarEvent]:
    service = _calendar_service()
    safe_days = min(max(days, 1), 30)
    safe_limit = min(max(max_results, 1), 25)
    now = datetime.now(UTC)
    time_min = now.isoformat().replace("+00:00", "Z")
    time_max = (now + timedelta(days=safe_days)).isoformat().replace("+00:00", "Z")

    try:
        response = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=safe_limit,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as exc:
        message = str(exc)
        if "calendar-json.googleapis.com" in message or "accessNotConfigured" in message:
            raise GmailIntegrationError(
                "Google Calendar API n'est pas activee dans ton projet Google Cloud. "
                f"Active-la ici: {CALENDAR_API_ENABLE_URL}"
            ) from exc
        raise GmailIntegrationError(f"Google Calendar indisponible: {message}") from exc

    items = response.get("items", [])
    if not isinstance(items, list):
        return []

    events: list[CalendarEvent] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        start = item.get("start", {})
        end = item.get("end", {})
        events.append(
            CalendarEvent(
                id=str(item.get("id", "")),
                summary=str(item.get("summary", "(sans titre)")),
                start=str(start.get("dateTime") or start.get("date") or ""),
                end=str(end.get("dateTime") or end.get("date") or ""),
                location=str(item.get("location", "")),
                html_link=str(item.get("htmlLink", "")),
            )
        )
    return events


def calendar_event_to_dict(event: CalendarEvent) -> dict[str, str]:
    return {
        "id": event.id,
        "summary": event.summary,
        "start": event.start,
        "end": event.end,
        "location": event.location,
        "html_link": event.html_link,
    }

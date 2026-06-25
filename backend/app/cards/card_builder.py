import re
import unicodedata
import uuid
from typing import Any

from app.cards.card_types import Card, CardAction, CardItem

_SLOT_PATTERN = re.compile(
    r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche"
    r"|aujourd'?hui|demain|ce soir|cet apres-midi|cet apres midi)\b"
    r"(?:\s+(?:a|le|au|vers|à))?\s*(\d{1,2}[h:]\d{0,2}(?:\d{2})?)",
    re.IGNORECASE,
)

_TASK_PATTERN = re.compile(
    r"^(?:\d+\.|[-•*])\s+(?:\[[ x]\]\s*)?(.{10,140})$",
    re.MULTILINE,
)

_MAIL_BLOCK_PATTERN = re.compile(
    r"(?:(?:mail|e-?mail|message|objet)\s*:?\s*(?:de|from|sujet|subject)?\s*[:\-]?\s*)"
    r"([^\n]{5,80})",
    re.IGNORECASE,
)

_EVENT_PATTERN = re.compile(
    r"(\d{1,2}[h:]\d{0,2}(?:\d{2})?)"
    r"(?:\s*[-–]\s*\d{1,2}[h:]\d{0,2}(?:\d{2})?)?"
    r"\s+[—\-–]?\s*(.{5,80})",
)

_DAY_LABEL = {
    "lundi": "Lundi",
    "mardi": "Mardi",
    "mercredi": "Mercredi",
    "jeudi": "Jeudi",
    "vendredi": "Vendredi",
    "samedi": "Samedi",
    "dimanche": "Dimanche",
    "aujourd": "Aujourd'hui",
    "demain": "Demain",
    "ce soir": "Ce soir",
    "cet apres": "Cet après-midi",
}


def _norm(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(c)
    )


def _uid() -> str:
    return str(uuid.uuid4())[:8]


def _extract_task_card(content: str) -> Card | None:
    matches = _TASK_PATTERN.findall(content)
    clean = []
    seen: set[str] = set()
    for m in matches:
        text = m.strip().rstrip(".")
        if text and text not in seen and len(text) > 8:
            seen.add(text)
            clean.append(text)
    if len(clean) < 2:
        return None

    items = [
        CardItem(id=_uid(), text=t, status="pending")
        for t in clean[:6]
    ]
    return Card(
        id=_uid(),
        type="task",
        title="Actions prioritaires",
        color="blue",
        items=items,
        actions=[CardAction(label="Tout marquer fait", action_key="mark_all_done")],
    )


def _extract_rdv_card(content: str) -> Card | None:
    norm = _norm(content)
    matches = _SLOT_PATTERN.findall(norm)
    seen: set[str] = set()
    slots: list[CardItem] = []
    for day_raw, time_raw in matches:
        day_key = day_raw[:6]
        day_label = next((v for k, v in _DAY_LABEL.items() if day_key.startswith(k[:5])), day_raw.capitalize())
        time_clean = time_raw.replace(":", "h").rstrip("h") + ("" if "h" in time_raw else "h")
        label = f"{day_label} {time_clean}"
        if label not in seen:
            seen.add(label)
            slots.append(CardItem(id=_uid(), text=label, status="pending"))
    if len(slots) < 2:
        return None

    return Card(
        id=_uid(),
        type="rdv_slot",
        title="Créneaux proposés",
        subtitle="Sélectionne un créneau pour confirmer",
        color="purple",
        items=slots[:4],
        actions=[CardAction(label="Ouvrir le calendrier", action_key="open_calendar")],
    )


def _extract_calendar_card(content: str) -> Card | None:
    matches = _EVENT_PATTERN.findall(content)
    items: list[CardItem] = []
    seen: set[str] = set()
    for time_raw, label in matches:
        text = f"{time_raw.replace(':', 'h')} — {label.strip()}"
        if text not in seen and len(label.strip()) > 4:
            seen.add(text)
            items.append(CardItem(id=_uid(), text=text, status="pending"))
    if not items:
        return None

    return Card(
        id=_uid(),
        type="calendar",
        title="Agenda",
        color="green",
        items=items[:5],
        actions=[CardAction(label="Ouvrir Google Calendar", action_key="open_calendar")],
    )


def _extract_mail_card(content: str) -> Card | None:
    # Look for bold names followed by dash (common format: **Expéditeur** — Sujet)
    bold_pattern = re.compile(r"\*\*([^*]{2,50})\*\*\s*[—\-–]\s*(.{5,100})")
    matches = bold_pattern.findall(content)
    items: list[CardItem] = []
    seen: set[str] = set()
    for sender, subject in matches:
        text = f"{sender.strip()} — {subject.strip()}"
        if text not in seen:
            seen.add(text)
            status = "urgent" if any(w in subject.lower() for w in ("urgent", "important", "relance", "asap")) else "pending"
            items.append(CardItem(id=_uid(), text=text, status=status))

    if not items:
        plain = _MAIL_BLOCK_PATTERN.findall(content)
        for m in plain[:4]:
            text = m.strip()
            if text not in seen:
                seen.add(text)
                items.append(CardItem(id=_uid(), text=text, status="pending"))

    if not items:
        return None

    return Card(
        id=_uid(),
        type="mail",
        title="Mails importants",
        color="amber",
        items=items[:5],
        actions=[
            CardAction(label="Ouvrir Gmail", action_key="open_gmail"),
            CardAction(label="Répondre", action_key="draft_reply"),
        ],
    )


def build_cards(content: str, route: str) -> list[dict[str, Any]]:
    cards: list[Card] = []

    if route == "calendar_read":
        cal = _extract_calendar_card(content)
        if cal:
            cards.append(cal)
        rdv = _extract_rdv_card(content)
        if rdv:
            cards.append(rdv)

    elif route in {"gmail_read", "gmail_reply_audit", "gmail_reply_draft"}:
        mail = _extract_mail_card(content)
        if mail:
            cards.append(mail)

    else:
        task = _extract_task_card(content)
        if task:
            cards.append(task)
        rdv = _extract_rdv_card(content)
        if rdv:
            cards.append(rdv)

    return [c.to_dict() for c in cards]

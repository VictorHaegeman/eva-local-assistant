"""
Pipeline de triage email autonome.

Pour chaque email non-bruit non-repondu :
  1. Genere un brouillon complet dans le style de Victor
  2. Cree le brouillon dans Gmail
  3. Retourne un rapport que le heartbeat pousse dans le chat
"""
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.integrations.email_classifier import classify_email
from app.integrations.gmail_client import (
    GmailIntegrationError,
    GmailMessage,
    create_gmail_reply_draft,
    find_sent_examples,
    format_email_for_prompt,
    format_sent_examples_for_prompt,
    get_gmail_message,
    get_gmail_thread_messages,
    gmail_status,
    list_gmail_messages,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.profile_store import build_profile_prompt_context


class EmailTriageError(Exception):
    pass


AUTO_SENDER_MARKERS = (
    "no-reply", "noreply", "do-not-reply",
    "notification", "newsletter", "alert", "alerts",
    "marketing", "promo", "support@", "auto-",
)

SENSITIVE_MARKERS = (
    "mot de passe", "password", "iban", "rib",
    "paiement", "payment", "facture", "invoice",
    "contrat", "contract", "juridique", "legal",
    "bail", "salaire", "salary", "impot", "tax",
)


@dataclass
class TriageEntry:
    message_id: str
    subject: str
    sender: str
    action: str  # "drafted" | "skipped" | "error"
    reason: str
    draft_created: bool = False
    draft_subject: str = ""
    draft_preview: str = ""


def _is_auto_sender(message: GmailMessage) -> bool:
    combined = f"{message.sender} {message.sender_email} {message.reply_to_email}".lower()
    return any(m in combined for m in AUTO_SENDER_MARKERS)


def _has_sensitive_content(message: GmailMessage) -> str:
    text = f"{message.subject} {message.snippet} {message.body[:2000]}".lower()
    for marker in SENSITIVE_MARKERS:
        if marker in text:
            return marker
    return ""


def _already_replied(message: GmailMessage) -> bool:
    try:
        thread = get_gmail_thread_messages(message.thread_id)
        for tm in thread:
            if tm.id == message.id:
                continue
            if "SENT" not in tm.label_ids:
                continue
            if message.internal_date and tm.internal_date > message.internal_date:
                return True
    except Exception:
        pass
    return False


def _skip_reason(message: GmailMessage) -> str:
    if _is_auto_sender(message):
        return "expediteur automatique"
    marker = _has_sensitive_content(message)
    if marker:
        return f"contenu sensible: {marker}"
    if _already_replied(message):
        return "deja repondu"
    try:
        classification = classify_email(message, include_body=True)
        if classification.is_noise:
            return f"bruit: {classification.category}"
    except Exception:
        pass
    body = message.body or message.snippet or ""
    if len(body) < 10:
        return "email vide"
    return ""


async def _generate_draft(message: GmailMessage) -> tuple[str, str]:
    """Returns (subject, body). Raises OllamaClientError on failure."""
    profile_ctx = build_profile_prompt_context()

    try:
        examples = find_sent_examples(message.sender_email, max_results=5)
        if len(examples) < 2:
            broader = find_sent_examples("", max_results=8)
            seen = {e.id for e in examples}
            examples = examples + [e for e in broader if e.id not in seen]
        examples_text = format_sent_examples_for_prompt(examples[:3]) if examples else "(aucun exemple)"
    except Exception:
        examples_text = "(exemples indisponibles)"

    prompt = f"""Tu rediges un brouillon de reponse email pour Victor. Retourne UNIQUEMENT le format suivant, rien d'autre.

Regles absolues:
- Tu reponds comme Victor, jamais comme l'expediteur
- Sois direct, professionnel, chaleureux si appropriate
- N'invente aucun fait, prix, date, promesse, piece jointe ou information absente du mail
- Maximum 160 mots dans le corps
- Reponds dans la meme langue que le mail recu

Format obligatoire (exactement ces deux lignes d'entete puis le corps):
Objet: [objet de ta reponse]
Corps:
[corps de la reponse]

Profil de Victor:
{profile_ctx}

Mail recu:
{format_email_for_prompt(message)}

Exemples envoyes par Victor (pour le style uniquement):
{examples_text}
""".strip()

    raw = await ask_ollama([{"role": "user", "content": prompt}], temperature=0.25)
    raw = raw.strip()

    subject = message.subject or "(sans objet)"
    body = raw

    lines = raw.split("\n")
    body_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("objet:"):
            subject = stripped[len("objet:"):].strip()
        elif stripped.lower() == "corps:":
            body_start = i + 1
            break

    if body_start is not None:
        body = "\n".join(lines[body_start:]).strip()

    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    return subject, body


async def run_autonomous_triage(max_emails: int = 5) -> dict[str, Any]:
    """
    Triage complet : lit l'inbox, redige un brouillon pour chaque email
    qui en a besoin, cree les brouillons dans Gmail.

    Retourne un rapport structure pour le heartbeat.
    """
    status = gmail_status()
    if not status.get("enabled"):
        return {"status": "disabled", "reason": "Gmail desactive", "results": [], "drafted_count": 0}
    if not status.get("available"):
        return {"status": "unavailable", "reason": "Gmail non connecte", "results": [], "drafted_count": 0}

    try:
        shallow_list = list_gmail_messages(
            query="in:inbox newer_than:7d -category:promotions -category:social",
            max_results=max_emails * 2,
        )
    except GmailIntegrationError as exc:
        return {"status": "error", "reason": str(exc), "results": [], "drafted_count": 0}

    results: list[TriageEntry] = []
    drafted_count = 0

    for shallow in shallow_list[:max_emails]:
        try:
            message = get_gmail_message(shallow.id)
        except GmailIntegrationError:
            continue

        skip = _skip_reason(message)
        if skip:
            results.append(TriageEntry(
                message_id=message.id,
                subject=message.subject,
                sender=message.sender_name or message.sender_email,
                action="skipped",
                reason=skip,
            ))
            continue

        try:
            subject, body = await _generate_draft(message)
        except OllamaClientError as exc:
            results.append(TriageEntry(
                message_id=message.id,
                subject=message.subject,
                sender=message.sender_name or message.sender_email,
                action="error",
                reason=f"Ollama: {exc}",
            ))
            continue

        if not body or len(body) < 20:
            results.append(TriageEntry(
                message_id=message.id,
                subject=message.subject,
                sender=message.sender_name or message.sender_email,
                action="skipped",
                reason="brouillon vide genere",
            ))
            continue

        try:
            create_gmail_reply_draft(message, body=body, subject=subject, open_in_browser=False)
            results.append(TriageEntry(
                message_id=message.id,
                subject=message.subject,
                sender=message.sender_name or message.sender_email,
                action="drafted",
                reason="brouillon cree automatiquement",
                draft_created=True,
                draft_subject=subject,
                draft_preview=body[:200],
            ))
            drafted_count += 1
        except GmailIntegrationError as exc:
            results.append(TriageEntry(
                message_id=message.id,
                subject=message.subject,
                sender=message.sender_name or message.sender_email,
                action="error",
                reason=f"Gmail API: {exc}",
            ))

    return {
        "status": "ok",
        "checked": len(results),
        "drafted_count": drafted_count,
        "skipped_count": sum(1 for r in results if r.action == "skipped"),
        "error_count": sum(1 for r in results if r.action == "error"),
        "results": [
            {
                "message_id": r.message_id,
                "subject": r.subject,
                "sender": r.sender,
                "action": r.action,
                "reason": r.reason,
                "draft_created": r.draft_created,
                "draft_subject": r.draft_subject,
            }
            for r in results
        ],
    }


def build_triage_proactive_message(report: dict[str, Any]) -> str:
    drafted = report.get("drafted_count", 0)
    checked = report.get("checked", 0)
    results = report.get("results", [])

    if drafted == 0:
        return f"**Triage inbox** — {checked} email(s) verifie(s), aucun brouillon necessaire."

    drafted_entries = [r for r in results if r.get("draft_created")]
    lines = [f"**Triage inbox** — {drafted} brouillon(s) prepares dans Gmail:"]
    for entry in drafted_entries[:5]:
        sender = entry.get("sender", "?")
        subject = entry.get("draft_subject") or entry.get("subject", "?")
        lines.append(f"- **{sender}** → {subject}")
    lines.append("Verifie et envoie depuis Gmail.")
    return "\n".join(lines)

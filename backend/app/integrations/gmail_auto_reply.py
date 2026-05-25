import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.config import settings
from app.integrations.email_classifier import classify_email
from app.integrations.gmail_client import (
    GMAIL_SEND_SCOPE,
    GmailIntegrationError,
    GmailMessage,
    create_gmail_reply_draft,
    find_sent_examples,
    format_email_for_prompt,
    format_sent_examples_for_prompt,
    get_gmail_message,
    get_gmail_thread_messages,
    gmail_status,
    google_token_scope_status,
    list_gmail_messages,
    message_to_dict,
    send_gmail_reply,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama_json
from app.memory.profile_store import build_profile_prompt_context


class GmailAutoReplyError(Exception):
    """Raised when the Gmail auto-reply loop cannot run."""


@dataclass(frozen=True)
class AutoReplyDecision:
    action: str
    confidence: float
    reason: str
    language: str
    subject: str
    body: str
    similarity: float
    examples_used: int


SENSITIVE_MARKERS = (
    "mot de passe",
    "password",
    "code de securite",
    "security code",
    "2fa",
    "verification",
    "iban",
    "rib",
    "paiement",
    "payment",
    "facture",
    "invoice",
    "contrat",
    "contract",
    "juridique",
    "legal",
    "litige",
    "plainte",
    "complaint",
    "refund",
    "remboursement",
    "resiliation",
    "annulation",
    "bail",
    "appartement",
    "location",
    "salaire",
    "salary",
    "impot",
    "tax",
)

AUTO_SENDER_MARKERS = (
    "no-reply",
    "noreply",
    "do-not-reply",
    "notification",
    "newsletter",
    "alert",
    "alerts",
    "marketing",
    "promo",
)

FR_MARKERS = (
    "bonjour",
    "merci",
    "cordialement",
    "vous",
    "votre",
    "reponse",
    "rendez-vous",
    "demande",
)

EN_MARKERS = (
    "hello",
    "hi",
    "thanks",
    "thank you",
    "regards",
    "you",
    "your",
    "meeting",
    "request",
)

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "vous",
    "nous",
    "pour",
    "avec",
    "dans",
    "des",
    "les",
    "une",
    "mon",
    "ton",
    "sur",
    "pas",
    "que",
    "qui",
    "est",
    "are",
    "have",
    "has",
}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _detect_language(text: str) -> str:
    normalized = _normalize(text)
    fr_score = sum(1 for marker in FR_MARKERS if marker in normalized)
    en_score = sum(1 for marker in EN_MARKERS if marker in normalized)
    if re.search(r"[éèêàùçôîï]", text, re.I):
        fr_score += 2
    return "en" if en_score > fr_score else "fr"


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", normalized)
        if token not in STOPWORDS
    }


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    denominator = math.sqrt(len(left_tokens) * len(right_tokens))
    return round(overlap / denominator, 3) if denominator else 0.0


def _is_auto_sender(message: GmailMessage) -> bool:
    sender = _normalize(" ".join([message.sender, message.sender_email, message.reply_to_email]))
    return any(marker in sender for marker in AUTO_SENDER_MARKERS)


def _thread_has_later_sent_reply(message: GmailMessage) -> bool:
    thread_messages = get_gmail_thread_messages(message.thread_id)
    for thread_message in thread_messages:
        if thread_message.id == message.id:
            continue
        if "SENT" not in thread_message.label_ids:
            continue
        if message.internal_date and thread_message.internal_date <= message.internal_date:
            continue
        return True
    return False


def _hard_skip_reason(message: GmailMessage) -> str:
    classification = classify_email(message, include_body=True)
    text = _normalize(" ".join([message.sender, message.sender_email, message.subject, message.snippet, message.body[:3000]]))

    if classification.is_noise:
        return f"mail classe bruit: {classification.category}"
    if _is_auto_sender(message):
        return "expediteur automatique/no-reply"
    if _thread_has_later_sent_reply(message):
        return "thread deja repondu par Victor"
    if len(message.body or message.snippet) > 5000:
        return "mail trop long pour auto-envoi fiable"
    for marker in SENSITIVE_MARKERS:
        if marker in text:
            return f"sujet sensible detecte: {marker}"
    return ""


def _json_from_text(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        cleaned = match.group(0)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GmailAutoReplyError("Decision auto-reply invalide: JSON absent.") from exc
    return payload if isinstance(payload, dict) else {}


def _coerce_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _rank_examples(original: GmailMessage, examples: list[GmailMessage]) -> list[tuple[GmailMessage, float]]:
    source_text = " ".join([original.subject, original.snippet, original.body[:3000]])
    ranked = [
        (example, _similarity(source_text, " ".join([example.subject, example.snippet, example.body[:3000]])))
        for example in examples
    ]
    return sorted(ranked, key=lambda item: item[1], reverse=True)


async def evaluate_auto_reply_candidate(message: GmailMessage) -> AutoReplyDecision:
    hard_skip = _hard_skip_reason(message)
    if hard_skip:
        return AutoReplyDecision(
            action="skip",
            confidence=0.0,
            reason=hard_skip,
            language=_detect_language(message.body or message.snippet),
            subject="",
            body="",
            similarity=0.0,
            examples_used=0,
        )

    examples = find_sent_examples(message.sender_email, max_results=settings.eva_gmail_max_sent_examples)
    if len(examples) < settings.eva_gmail_auto_reply_min_sent_examples:
        broader_examples = find_sent_examples("", max_results=settings.eva_gmail_max_sent_examples)
        examples = examples + [item for item in broader_examples if item.id not in {example.id for example in examples}]

    ranked_examples = _rank_examples(message, examples)
    best_similarity = ranked_examples[0][1] if ranked_examples else 0.0
    selected_examples = [example for example, score in ranked_examples[:3] if score >= 0.12]
    if len(selected_examples) < settings.eva_gmail_auto_reply_min_sent_examples:
        return AutoReplyDecision(
            action="draft",
            confidence=0.0,
            reason="pas assez d'exemples envoyes similaires",
            language=_detect_language(message.body or message.snippet),
            subject="",
            body="",
            similarity=best_similarity,
            examples_used=len(selected_examples),
        )

    source_language = _detect_language(message.body or message.snippet)
    prompt = f"""
Tu es le garde-fou d'envoi autonome Gmail d'Eva.
Retourne uniquement un JSON valide.

Objectif: decider si Eva peut envoyer SEULE une reponse tres evidente.

Regles strictes:
- decision = "send" seulement si la reponse est courte, non sensible, evidente et deja couverte par les exemples de Victor.
- Si tu as le moindre doute: decision = "draft" ou "skip".
- Reponds dans la langue du mail source: {source_language}.
- N'invente aucun fait, prix, rendez-vous, promesse, piece jointe ou information absente.
- Pas d'envoi pour facture, paiement, contrat, logement, juridique, plainte, securite, mot de passe.
- Corps max 140 mots.

JSON attendu:
{{
  "decision": "send|draft|skip",
  "confidence": 0.0,
  "reason": "raison courte",
  "language": "fr|en",
  "subject": "objet",
  "body": "reponse email"
}}

Profil local:
{build_profile_prompt_context()}

Mail recu:
{format_email_for_prompt(message)}

Exemples envoyes par Victor:
{format_sent_examples_for_prompt(selected_examples)}
""".strip()

    try:
        payload = await ask_ollama_json(
            "Tu es un filtre Gmail local. Tu retournes uniquement du JSON.",
            prompt,
            temperature=0.1,
        )
    except OllamaClientError as exc:
        raise GmailAutoReplyError(str(exc)) from exc
    action = str(payload.get("decision") or payload.get("action") or "draft").strip().lower()
    if action not in {"send", "draft", "skip"}:
        action = "draft"
    language = str(payload.get("language") or source_language).strip().lower()
    if language not in {"fr", "en"}:
        language = source_language
    confidence = _coerce_confidence(payload.get("confidence"))
    subject = str(payload.get("subject") or message.subject).strip()
    body = str(payload.get("body") or "").strip()
    reason = str(payload.get("reason") or "decision LLM").strip()

    if language != source_language:
        action = "draft"
        reason = f"langue incoherente: source={source_language}, reponse={language}"
    if best_similarity < settings.eva_gmail_auto_reply_min_similarity:
        action = "draft"
        reason = f"similarite trop faible avec les reponses passees: {best_similarity}"
    if confidence < settings.eva_gmail_auto_reply_min_confidence:
        action = "draft" if action == "send" else action
        reason = f"confiance insuffisante: {confidence}"
    if not body:
        action = "skip"
        reason = "corps de reponse vide"
    if len(body) > 1800:
        action = "draft"
        reason = "reponse trop longue pour auto-envoi"

    return AutoReplyDecision(
        action=action,
        confidence=confidence,
        reason=reason,
        language=language,
        subject=subject,
        body=body,
        similarity=best_similarity,
        examples_used=len(selected_examples),
    )


def _decision_to_dict(decision: AutoReplyDecision) -> dict[str, object]:
    return {
        "action": decision.action,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "language": decision.language,
        "subject": decision.subject,
        "body": decision.body,
        "similarity": decision.similarity,
        "examples_used": decision.examples_used,
    }


async def run_gmail_auto_reply_once(max_results: int = 10, dry_run: bool = False) -> dict[str, object]:
    status = gmail_status()
    if not status.get("enabled"):
        return {"status": "disabled", "reason": "EVA_GMAIL_ENABLED=false", "sent": [], "skipped": []}
    if not settings.eva_gmail_auto_send_obvious_replies:
        return {"status": "disabled", "reason": "auto-reponse Gmail desactivee", "sent": [], "skipped": []}
    if not settings.eva_allow_auto_external_send:
        return {
            "status": "blocked",
            "reason": "EVA_ALLOW_AUTO_EXTERNAL_SEND=false",
            "sent": [],
            "skipped": [],
        }

    send_scope = google_token_scope_status([GMAIL_SEND_SCOPE])
    if not send_scope["has_required_scopes"]:
        return {
            "status": "blocked",
            "reason": "scope Gmail send manquant: reconnecte Gmail avec les nouveaux scopes",
            "missing_scopes": send_scope["missing_scopes"],
            "sent": [],
            "skipped": [],
        }

    limit = min(max(max_results, 1), 25)
    messages = list_gmail_messages(query=settings.eva_gmail_auto_reply_query, max_results=limit)
    sent: list[dict[str, object]] = []
    drafted: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    for shallow in messages:
        if len(sent) >= settings.eva_gmail_auto_reply_max_per_run:
            break
        original = get_gmail_message(shallow.id)
        decision = await evaluate_auto_reply_candidate(original)
        entry = {
            "message": message_to_dict(original),
            "decision": _decision_to_dict(decision),
        }

        if dry_run:
            skipped.append({**entry, "reason": "dry_run"})
            continue

        if decision.action == "send":
            try:
                delivery = send_gmail_reply(
                    original,
                    body=decision.body,
                    subject=decision.subject,
                    open_in_browser=settings.eva_gmail_auto_reply_open_sent_thread,
                )
            except GmailIntegrationError as exc:
                skipped.append({**entry, "reason": str(exc)})
                continue
            sent.append({**entry, "delivery": delivery})
        elif decision.action == "draft" and decision.confidence >= 0.72:
            try:
                draft = create_gmail_reply_draft(
                    original,
                    body=decision.body,
                    subject=decision.subject,
                    open_in_browser=False,
                )
                drafted.append({**entry, "draft": draft})
            except GmailIntegrationError as exc:
                skipped.append({**entry, "reason": str(exc)})
        else:
            skipped.append({**entry, "reason": decision.reason})

    return {
        "status": "ok",
        "query": settings.eva_gmail_auto_reply_query,
        "dry_run": dry_run,
        "checked": len(messages),
        "sent_count": len(sent),
        "drafted_count": len(drafted),
        "skipped_count": len(skipped),
        "sent": sent,
        "drafted": drafted,
        "skipped": skipped,
    }

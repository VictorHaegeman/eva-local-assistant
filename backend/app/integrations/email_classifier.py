import re
import unicodedata
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EmailClassification:
    category: str
    importance_score: int
    is_important: bool
    is_noise: bool
    reason: str
    recommended_action: str


IMPORTANT_MARKERS = {
    "dreamlense": 35,
    "dream lense": 35,
    "victor": 8,
    "prospect": 24,
    "client": 20,
    "contact": 16,
    "demande": 16,
    "rendez-vous": 24,
    "rdv": 24,
    "appel": 16,
    "devis": 26,
    "facture": 22,
    "paiement": 20,
    "contrat": 24,
    "proposition": 16,
    "collaboration": 18,
    "partenariat": 18,
    "urgent": 20,
    "important": 14,
    "relance": 16,
    "entretien": 18,
    "appartement": 16,
    "location": 12,
    "visite": 14,
}

PROMO_MARKERS = {
    "promotion": 28,
    "promo": 26,
    "soldes": 24,
    "reduction": 22,
    "offre speciale": 24,
    "black friday": 30,
    "cyber monday": 30,
    "code promo": 26,
    "newsletter": 28,
    "unsubscribe": 32,
    "desabonnement": 32,
    "se desabonner": 32,
    "bon plan": 22,
    "nouvelle collection": 18,
    "decouvrez nos offres": 20,
}

AUTOMATION_MARKERS = {
    "no-reply": 28,
    "noreply": 28,
    "do-not-reply": 28,
    "ne pas repondre": 24,
    "notification": 18,
    "alerte": 18,
    "automatique": 18,
    "security alert": 22,
    "code de securite": 20,
}

SOCIAL_MARKERS = {
    "linkedin": 14,
    "instagram": 12,
    "facebook": 12,
    "tiktok": 12,
    "nouveau follower": 18,
    "nouvel abonne": 18,
    "connexion": 12,
    "message linkedin": 20,
}

TRANSACTIONAL_MARKERS = {
    "recu": 14,
    "commande": 14,
    "livraison": 12,
    "reservation": 16,
    "confirmation": 12,
    "billet": 12,
    "invoice": 18,
    "receipt": 14,
}


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _contains_any(text: str, markers: dict[str, int]) -> list[tuple[str, int]]:
    return [(marker, weight) for marker, weight in markers.items() if marker in text]


def _sender_domain(sender_email: str) -> str:
    if "@" not in sender_email:
        return ""
    return sender_email.rsplit("@", 1)[-1].lower().strip()


def _sender_local_part(sender_email: str) -> str:
    if "@" not in sender_email:
        return ""
    return sender_email.split("@", 1)[0].lower().strip()


def _label_set(message: Any) -> set[str]:
    return {str(label).upper() for label in getattr(message, "label_ids", ()) if label}


def classify_email(message: Any, include_body: bool = False) -> EmailClassification:
    labels = _label_set(message)
    sender = str(getattr(message, "sender", "") or "")
    sender_email = str(getattr(message, "sender_email", "") or "")
    subject = str(getattr(message, "subject", "") or "")
    snippet = str(getattr(message, "snippet", "") or "")
    body = str(getattr(message, "body", "") or "")[:2500] if include_body else ""
    text = _normalize(" ".join([sender, sender_email, subject, snippet, body]))
    domain = _sender_domain(sender_email)
    local_part = _sender_local_part(sender_email)

    important_score = 0
    noise_score = 0
    reasons: list[str] = []

    if "IMPORTANT" in labels:
        important_score += 25
        reasons.append("label Gmail Important")
    if "STARRED" in labels:
        important_score += 20
        reasons.append("mail marque")
    if "CATEGORY_PRIMARY" in labels:
        important_score += 8
        reasons.append("categorie principale")
    if "CATEGORY_PROMOTIONS" in labels:
        noise_score += 45
        reasons.append("categorie Promotions")
    if "CATEGORY_SOCIAL" in labels:
        noise_score += 22
        reasons.append("categorie Social")
    if "CATEGORY_FORUMS" in labels:
        noise_score += 18
        reasons.append("categorie Forum")

    for marker, weight in _contains_any(text, IMPORTANT_MARKERS):
        important_score += weight
        if len(reasons) < 4:
            reasons.append(f"signal important: {marker}")

    for marker, weight in _contains_any(text, PROMO_MARKERS):
        noise_score += weight
        if len(reasons) < 4:
            reasons.append(f"signal pub/newsletter: {marker}")

    for marker, weight in _contains_any(text, AUTOMATION_MARKERS):
        noise_score += weight
        if len(reasons) < 4:
            reasons.append(f"signal automatique: {marker}")

    social_hits = _contains_any(text, SOCIAL_MARKERS)
    for marker, weight in social_hits:
        important_score += 6 if "message" in marker else 0
        noise_score += weight
        if len(reasons) < 4:
            reasons.append(f"signal social: {marker}")

    for marker, weight in _contains_any(text, TRANSACTIONAL_MARKERS):
        important_score += weight
        if len(reasons) < 4:
            reasons.append(f"signal transactionnel: {marker}")

    if subject.lower().startswith(("re:", "fw:", "fwd:")):
        important_score += 12
        reasons.append("conversation existante")

    automated_sender = re.search(
        r"(no-?reply|noreply|notification|newsletter|marketing|promo|news|alert|alerts|support)",
        local_part,
        re.I,
    )
    if sender_email and not automated_sender:
        important_score += 10
        if domain:
            reasons.append(f"expediteur humain probable: {domain}")

    raw_score = important_score - noise_score
    importance_score = max(0, min(100, 50 + raw_score))

    if noise_score >= 45 and important_score < 45:
        category = "pub"
        recommended_action = "ignorer sauf si Victor demande les promos"
    elif noise_score >= 35 and important_score < noise_score:
        category = "newsletter"
        recommended_action = "resumer seulement si le sujet touche les priorites de Victor"
    elif social_hits and important_score < 55:
        category = "social"
        recommended_action = "surveiller en brief, ne pas traiter comme email prioritaire"
    elif noise_score >= 28 and "CATEGORY_UPDATES" in labels:
        category = "notification"
        recommended_action = "extraire l'information utile sans repondre"
    elif any(marker in text for marker in ("facture", "paiement", "devis", "contrat", "reservation", "commande")):
        category = "transactionnel"
        recommended_action = "mettre en avant si action ou suivi necessaire"
    else:
        category = "important" if importance_score >= 62 else "normal"
        recommended_action = "lire et proposer une action si le contenu le justifie"

    is_noise = category in {"pub", "newsletter", "social"} and importance_score < 65
    is_important = not is_noise and importance_score >= 62

    reason = "; ".join(dict.fromkeys(reasons[:5])) or "aucun signal fort"
    return EmailClassification(
        category=category,
        importance_score=importance_score,
        is_important=is_important,
        is_noise=is_noise,
        reason=reason,
        recommended_action=recommended_action,
    )


def classification_to_dict(classification: EmailClassification) -> dict[str, object]:
    return {
        "category": classification.category,
        "importance_score": classification.importance_score,
        "is_important": classification.is_important,
        "is_noise": classification.is_noise,
        "reason": classification.reason,
        "recommended_action": classification.recommended_action,
    }

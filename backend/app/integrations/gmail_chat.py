import re
import unicodedata

from app.integrations.browser import open_url
from app.integrations.gmail_client import (
    GmailIntegrationError,
    GmailMessage,
    find_sent_examples,
    format_email_for_prompt,
    format_sent_examples_for_prompt,
    get_gmail_message,
    list_gmail_messages,
    message_to_dict,
)
from app.llm.ollama_client import OllamaClientError, ask_ollama
from app.memory.profile_store import build_profile_prompt_context


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _has_gmail_context(normalized: str) -> bool:
    return any(
        marker in normalized
        for marker in (
            "gmail",
            "boite mail",
            "boite email",
            "mes mails",
            "mes emails",
            "dernier mail",
            "dernier email",
            "mail recu",
            "email recu",
            "mail recu",
            "mail du prospect",
        )
    )


def _message_index_from_request(message: str) -> int:
    normalized = _normalize(message)
    if any(marker in normalized for marker in ("deuxieme", "2eme", "2e", "second")):
        return 1
    if any(marker in normalized for marker in ("troisieme", "3eme", "3e")):
        return 2
    if any(marker in normalized for marker in ("quatrieme", "4eme", "4e")):
        return 3
    return 0


def wants_gmail_open(message: str) -> bool:
    normalized = _normalize(message)
    open_markers = ("ouvre", "ouvrir", "open", "brave", "navigateur", "browser")
    return (
        _has_gmail_context(normalized)
        or ("mail" in normalized and any(marker in normalized for marker in open_markers))
    ) and any(marker in normalized for marker in open_markers)


def wants_gmail_list(message: str) -> bool:
    normalized = _normalize(message)
    return _has_gmail_context(normalized) and any(
        marker in normalized
        for marker in (
            "affiche",
            "donne",
            "lis",
            "lire",
            "montre",
            "dernier",
            "recents",
            "recus",
            "recu",
            "inbox",
            "boite",
            "boite mail",
            "liste",
        )
    )


def wants_gmail_inspect(message: str) -> bool:
    normalized = _normalize(message)
    ordinal_context = any(
        marker in normalized
        for marker in (
            "dernier mail",
            "dernier email",
            "premier mail",
            "deuxieme mail",
            "2eme mail",
            "2e mail",
            "second mail",
            "troisieme mail",
            "3eme mail",
            "3e mail",
        )
    )
    inspect_markers = (
        "analyse",
        "regarde",
        "resume",
        "resumer",
        "qu'est ce",
        "qu est ce",
        "ce qui",
        "contenu",
        "quoi",
        "detail",
        "dis moi",
    )
    return ordinal_context and any(marker in normalized for marker in inspect_markers)


def wants_gmail_reply_draft(message: str) -> bool:
    normalized = _normalize(message)
    if not _has_gmail_context(normalized):
        return False

    return any(marker in normalized for marker in ("repond", "reponse", "brouillon")) or (
        "redige" in normalized and any(marker in normalized for marker in ("reponse", "recu", "dernier"))
    )


def _gmail_thread_url(message: GmailMessage) -> str:
    thread = message.thread_id or message.id
    return f"https://mail.google.com/mail/u/0/#all/{thread}"


def _extract_urls(text: str) -> list[str]:
    if not text:
        return []
    candidates = re.findall(r"https?://[^\s)\]>\"']+", text)
    cleaned: list[str] = []
    seen = set()
    for candidate in candidates:
        url = candidate.rstrip(".,;")
        if url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


def _select_relevant_external_link(message: GmailMessage) -> str:
    text = "\n".join([message.subject, message.snippet, message.body])
    urls = _extract_urls(text)
    if not urls:
        return ""

    ignored = (
        "unsubscribe",
        "desabonnement",
        "preferences",
        "privacy",
        "facebook.com",
        "twitter.com",
        "instagram",
        "linkedin",
        "/static/",
        "logo",
        "transparent",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
    )
    priority_paths = ("/annonce", "/annonces", "voir_annonce", "voir-annonce")
    priority_domains = ("bienici.com", "pap.fr", "seloger.com", "leboncoin.fr")

    for url in urls:
        lowered = url.lower()
        if any(marker in lowered for marker in ignored):
            continue
        if any(marker in lowered for marker in priority_paths):
            return url

    for url in urls:
        lowered = url.lower()
        if any(marker in lowered for marker in ignored):
            continue
        if any(domain in lowered for domain in priority_domains):
            return url

    for url in urls:
        lowered = url.lower()
        if not any(marker in lowered for marker in ignored):
            return url

    return ""


def _looks_like_housing_message(message: GmailMessage) -> bool:
    text = _normalize(" ".join([message.subject, message.sender, message.snippet, message.body[:1500]]))
    return any(
        marker in text
        for marker in (
            "appartement",
            "studio",
            "location",
            "logement",
            "bienici",
            "pap.fr",
            "demande de contact",
            "alerte email",
        )
    )


def _looks_like_automated_message(message: GmailMessage) -> bool:
    text = _normalize(" ".join([message.subject, message.sender, message.sender_email, message.snippet, message.body[:1500]]))
    return any(
        marker in text
        for marker in (
            "no-reply",
            "noreply",
            "ne pas repondre",
            "ne repondez pas",
            "notification",
            "alerte email",
            "users-alertes",
            "demande de contact",
            "mail automatique",
        )
    )


def open_gmail_message_in_browser(message: GmailMessage, open_related_link: bool = False) -> dict[str, str]:
    gmail_url = _gmail_thread_url(message)
    open_url(gmail_url)

    related_link = ""
    if open_related_link:
        related_link = _select_relevant_external_link(message)
        if related_link:
            open_url(related_link)

    return {
        "gmail_url": gmail_url,
        "related_link": related_link,
    }


def format_gmail_message_list() -> str:
    messages = list_gmail_messages(max_results=5)
    if not messages:
        return "Source: Gmail API.\nJe n'ai trouve aucun mail recent dans Gmail."

    lines = [
        "Source: Gmail API, lecture seule.",
        "Derniers mails Gmail reels renvoyes par Google:",
    ]
    for index, message in enumerate(messages, start=1):
        lines.append(
            f"{index}. {message.subject}\n"
            f"   De: {message.sender}\n"
            f"   Date: {message.date}\n"
            f"   ID: {message.id}\n"
            f"   Extrait: {message.snippet}"
        )
    return "\n\n".join(lines)


async def build_gmail_chat_response(message: str, force_list: bool = False) -> str | None:
    open_requested = wants_gmail_open(message)
    inspect_requested = wants_gmail_inspect(message)
    reply_requested = wants_gmail_reply_draft(message)

    if open_requested or inspect_requested or reply_requested:
        selected_index = _message_index_from_request(message)
        messages = list_gmail_messages(max_results=max(5, selected_index + 1))
        if not messages:
            return "Source: Gmail API.\nJe n'ai trouve aucun mail recent a ouvrir ou traiter."

        if selected_index >= len(messages):
            return f"Source: Gmail API.\nJe n'ai trouve que {len(messages)} mail(s) recent(s), pas de mail numero {selected_index + 1}."

        original = get_gmail_message(messages[selected_index].id)
        lines = [
            "Source: Gmail API, lecture seule.",
            f"Mail source: {original.subject} ({original.sender})",
        ]

        should_open_related_link = open_requested and (
            "annonce" in _normalize(message) or _looks_like_housing_message(original)
        )
        if open_requested:
            opened = open_gmail_message_in_browser(
                original,
                open_related_link=should_open_related_link,
            )
            lines.append(f"J'ai ouvert le mail reel dans Brave: {opened['gmail_url']}")
            if opened["related_link"]:
                lines.append(f"J'ai aussi ouvert le lien pertinent detecte dans le mail: {opened['related_link']}")

        if _looks_like_housing_message(original):
            lines.append(
                "Lecture rapide: ce mail ressemble a un signal immobilier. "
                "Est-ce que tu cherches un nouvel appartement ? Si oui, je peux preparer un rendez-vous "
                "dans le calendrier, mais l'ajout restera a confirmer."
            )

        if not reply_requested:
            if inspect_requested and original.body:
                preview = original.body[:1200].strip()
                lines.append(f"Extrait lu dans le mail:\n{preview}")
            return "\n\n".join(lines)

        if _looks_like_automated_message(original):
            lines.extend(
                [
                    "Je ne prepare pas de faux brouillon de reponse: ce mail ressemble a une alerte, une notification ou une adresse automatique.",
                    "Action conseillee: traiter le lien ou le site source plutot que repondre directement a l'expediteur.",
                ]
            )
            if not should_open_related_link:
                related_link = _select_relevant_external_link(original)
                if related_link:
                    open_url(related_link)
                    lines.append(f"J'ai ouvert le lien le plus pertinent detecte: {related_link}")
            return "\n\n".join(lines)

        examples = find_sent_examples(original.sender_email)

        prompt = f"""
Tu dois rediger un brouillon de reponse email pour Victor.
Ne dis jamais que le mail a ete envoye.
La reponse doit etre prete a relire, modifier et valider par Victor.
Tu reponds comme Victor, jamais comme l'expediteur du mail.
Utilise uniquement le contenu du mail recu ci-dessous. N'invente pas de prix, surface, rendez-vous, adresse ou caracteristiques absentes.
Adresse expediteur verifiee: {original.sender_email}
Ne dis jamais que l'adresse est no-reply si l'adresse expediteur verifiee ne contient pas no-reply ou noreply.
Si le mail vient vraiment d'une adresse no-reply, d'une alerte automatique ou d'une notification, dis clairement que la reponse email directe est deconseillee et propose l'action la plus logique.

Profil local:
{build_profile_prompt_context()}

Instruction de Victor:
{message}

Mail recu:
{format_email_for_prompt(original)}

Exemples de mails deja envoyes par Victor:
{format_sent_examples_for_prompt(examples)}

Donne uniquement:
1. Diagnostic du mail;
2. Reponse conseillee: oui/non;
3. Brouillon uniquement si une reponse email a du sens;
4. Actions proposees a Victor.
""".strip()

        try:
            draft = await ask_ollama([{"role": "user", "content": prompt}])
        except OllamaClientError as exc:
            raise GmailIntegrationError(str(exc)) from exc

        lines.extend(["J'ai prepare une proposition, sans envoyer le mail.", draft])
        return "\n\n".join(lines)

    if force_list or wants_gmail_list(message):
        return format_gmail_message_list()

    return None


def gmail_message_dicts(query: str, max_results: int) -> list[dict[str, str]]:
    return [message_to_dict(message) for message in list_gmail_messages(query, max_results)]

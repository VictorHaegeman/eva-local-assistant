import re
import unicodedata

from app.integrations.browser import open_url
from app.integrations.gmail_client import (
    GmailIntegrationError,
    GmailMessage,
    create_gmail_reply_draft,
    find_sent_examples,
    format_email_for_prompt,
    format_sent_examples_for_prompt,
    get_gmail_message,
    get_gmail_thread_messages,
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
            "le mail",
            "ce mail",
            "au mail",
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


def wants_gmail_inbox_open(message: str) -> bool:
    normalized = _normalize(message)
    if not any(marker in normalized for marker in ("ouvre", "ouvrir", "open", "brave", "navigateur")):
        return False
    return any(marker in normalized for marker in ("mes mails", "mes emails", "boite mail", "boite email", "inbox", "gmail"))


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
    if _has_reply_audit_context(normalized):
        return False

    reply_markers = (
        "repond",
        "reponse",
        "brouillon",
        "redige",
        "ecris",
        "ecrit",
        "prepare",
        "pret a etre envoye",
        "pret a envoyer",
        "a approuver",
        "bouton repondre",
        "direct dans mes mails",
        "dans mes mails",
    )
    has_strong_context = _has_gmail_context(normalized)
    has_weak_reply_context = "mail" in normalized and any(
        marker in normalized for marker in ("repond", "reponse", "brouillon")
    )
    if not has_strong_context and not has_weak_reply_context:
        return False

    return any(marker in normalized for marker in reply_markers)


def _has_reply_audit_context(normalized: str) -> bool:
    return any(
        marker in normalized
        for marker in (
            "pas repondu",
            "non repondu",
            "sans reponse",
            "sans repondre",
            "a repondre",
            "a traiter",
            "que j'ai pas repondu",
            "que je n'ai pas repondu",
        )
    )


def wants_gmail_reply_audit(message: str) -> bool:
    normalized = _normalize(message)
    if not _has_gmail_context(normalized) and "mails" not in normalized:
        return False
    return _has_reply_audit_context(normalized)


def parse_reply_draft(raw_draft: str, original_subject: str) -> tuple[str, str]:
    subject = ""
    body = raw_draft.strip()

    subject_match = re.search(
        r"(?im)^\s*(?:objet|subject)\s*:\s*(?P<subject>.+?)\s*$",
        raw_draft,
    )
    body_match = re.search(
        r"(?is)^\s*(?:corps|body)\s*:\s*(?P<body>.+)$",
        raw_draft,
    )

    if subject_match:
        subject = subject_match.group("subject").strip()
    if body_match:
        body = body_match.group("body").strip()

    if not subject:
        clean_subject = original_subject.strip() or "(sans objet)"
        subject = clean_subject if clean_subject.lower().startswith("re:") else f"Re: {clean_subject}"

    return subject, body


def _gmail_thread_url(message: GmailMessage) -> str:
    thread = message.thread_id or message.id
    return f"https://mail.google.com/mail/u/0/#all/{thread}"


def _gmail_inbox_url() -> str:
    return "https://mail.google.com/mail/u/0/#inbox"


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


def open_gmail_inbox_in_browser() -> str:
    url = _gmail_inbox_url()
    open_url(url)
    return url


def format_gmail_message_list() -> str:
    messages = list_gmail_messages(max_results=5)
    if not messages:
        return "Source: Gmail API.\nJe n'ai trouve aucun mail recent dans Gmail."

    lines = [
        "Source: Gmail API, inbox reelle.",
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


def _extract_topic_from_message(message: str) -> str:
    normalized = _normalize(message)
    if "dreamlense" in normalized or "dream lense" in normalized:
        return "DreamLense"

    match = re.search(
        r"(?i)(?:concern(?:e|ant)?|sur|a propos de|à propos de)\s+(?P<topic>[A-Za-z0-9_.@ -]{3,80})",
        message,
    )
    if match:
        topic = match.group("topic").strip(" ?!.,;:-")
        topic = re.sub(r"\b(?:et|dis|moi|si|j'ai|je|n'ai|pas|repondu|répondu).*$", "", topic, flags=re.IGNORECASE).strip()
        if topic:
            return topic

    return ""


def _topic_queries(topic: str) -> list[str]:
    if topic.lower() == "dreamlense":
        return [
            'newer_than:365d -in:sent "DreamLense"',
            'newer_than:365d -in:sent dreamlense-ai.com',
            'newer_than:365d -in:sent dreamlense',
        ]

    escaped = topic.replace('"', "")
    return [f'newer_than:365d -in:sent "{escaped}"']


def _list_topic_messages(topic: str, max_results: int = 8) -> list[GmailMessage]:
    seen: set[str] = set()
    messages: list[GmailMessage] = []
    for query in _topic_queries(topic):
        for message in list_gmail_messages(query=query, max_results=max_results):
            if message.id in seen:
                continue
            seen.add(message.id)
            messages.append(message)
        if messages:
            break
    return messages[:max_results]


def _thread_has_victor_reply(original: GmailMessage) -> bool:
    thread_messages = get_gmail_thread_messages(original.thread_id)
    for thread_message in thread_messages:
        if thread_message.id == original.id:
            continue
        if "SENT" not in thread_message.label_ids:
            continue
        if original.internal_date and thread_message.internal_date <= original.internal_date:
            continue
        return True
    return False


def build_gmail_reply_audit_response(message: str) -> str:
    topic = _extract_topic_from_message(message) or "ta demande"
    messages = _list_topic_messages(topic)
    if not messages:
        return (
            "Interpretation Eva: tu veux que je lise les mails reels et que je verifie les fils sans reponse.\n\n"
            f"Source: Gmail API.\nJe n'ai trouve aucun mail recent lie a {topic}."
        )

    unanswered: list[GmailMessage] = []
    answered: list[GmailMessage] = []
    checked: list[tuple[GmailMessage, bool]] = []
    for shallow_message in messages:
        full_message = get_gmail_message(shallow_message.id)
        replied = _thread_has_victor_reply(full_message)
        checked.append((full_message, replied))
        if replied:
            answered.append(full_message)
        else:
            unanswered.append(full_message)

    lines = [
        "Interpretation Eva: tu veux un audit Gmail, pas une configuration OAuth ni un brouillon automatique.",
        f"Source: Gmail API. Sujet recherche: {topic}.",
        f"Mails verifies: {len(checked)}. Sans reponse detectee: {len(unanswered)}.",
        "",
    ]

    if unanswered:
        lines.append("A traiter:")
        for index, item in enumerate(unanswered[:5], start=1):
            lines.append(
                f"{index}. {item.subject}\n"
                f"   De: {item.sender}\n"
                f"   Date: {item.date}\n"
                f"   ID: {item.id}\n"
                f"   Extrait: {item.snippet}"
            )
        lines.append("")
        lines.append("Tu peux me dire: `reponds au mail ID ...` ou `ouvre le premier mail DreamLense`.")
    else:
        lines.append("Je n'ai pas detecte de mail DreamLense recent sans reponse de ta part.")

    if answered:
        lines.append("")
        lines.append("Deja repondu:")
        for item in answered[:5]:
            lines.append(f"- {item.subject} ({item.date})")

    return "\n".join(lines)


async def build_gmail_chat_response(message: str, force_list: bool = False) -> str | None:
    reply_audit_requested = wants_gmail_reply_audit(message)
    if reply_audit_requested:
        return build_gmail_reply_audit_response(message)

    inbox_open_requested = wants_gmail_inbox_open(message)
    open_requested = wants_gmail_open(message)
    inspect_requested = wants_gmail_inspect(message)
    reply_requested = wants_gmail_reply_draft(message)

    if inbox_open_requested and not inspect_requested and not reply_requested:
        url = open_gmail_inbox_in_browser()
        return (
            "Interpretation Eva: tu veux ouvrir ta boite Gmail, pas traiter un mail precis.\n\n"
            f"J'ai ouvert Gmail dans Brave: {url}"
        )

    if open_requested or inspect_requested or reply_requested:
        selected_index = _message_index_from_request(message)
        messages = list_gmail_messages(max_results=max(5, selected_index + 1))
        if not messages:
            return "Source: Gmail API.\nJe n'ai trouve aucun mail recent a ouvrir ou traiter."

        if selected_index >= len(messages):
            return f"Source: Gmail API.\nJe n'ai trouve que {len(messages)} mail(s) recent(s), pas de mail numero {selected_index + 1}."

        original = get_gmail_message(messages[selected_index].id)
        source_label = "Source: Gmail API + brouillon Gmail." if reply_requested else "Source: Gmail API, inbox reelle."
        lines = [source_label, f"Mail source: {original.subject} ({original.sender})"]

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
                    "Je ne cree pas de faux brouillon de reponse: ce mail ressemble a une alerte, une notification ou une adresse automatique.",
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
La reponse va etre creee comme brouillon reel dans Gmail, mais jamais envoyee automatiquement.
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

Format obligatoire:
Objet: ...
Corps:
...
""".strip()

        try:
            draft = await ask_ollama([{"role": "user", "content": prompt}])
        except OllamaClientError as exc:
            raise GmailIntegrationError(str(exc)) from exc

        subject, body = parse_reply_draft(draft, original.subject)
        try:
            gmail_draft = create_gmail_reply_draft(
                original,
                body=body,
                subject=subject,
                open_in_browser=True,
            )
        except GmailIntegrationError as exc:
            lines.extend(
                [
                    "J'ai redige le contenu, mais je n'ai pas pu creer le brouillon dans Gmail.",
                    str(exc),
                    "Action a faire: ouvre le panneau Gmail et clique `Reconnecter scopes` pour donner le scope gmail.compose.",
                    "",
                    f"Objet: {subject}",
                    "Corps:",
                    body,
                ]
            )
            return "\n\n".join(lines)

        lines.extend(
            [
                "Brouillon reel cree dans Gmail. Je ne l'ai pas envoye.",
                f"Destinataire: {gmail_draft['to']}",
                f"Objet: {gmail_draft['subject']}",
                f"Fil Gmail ouvert dans Brave: {gmail_draft['thread_url']}",
                "Tu peux relire/modifier puis cliquer Envoyer toi-meme dans Gmail.",
            ]
        )
        return "\n\n".join(lines)

    if force_list or wants_gmail_list(message):
        return format_gmail_message_list()

    return None


def gmail_message_dicts(query: str, max_results: int) -> list[dict[str, str]]:
    return [message_to_dict(message) for message in list_gmail_messages(query, max_results)]

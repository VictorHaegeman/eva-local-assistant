import unicodedata

from app.integrations.gmail_client import (
    GmailIntegrationError,
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


def wants_gmail_reply_draft(message: str) -> bool:
    normalized = _normalize(message)
    if not _has_gmail_context(normalized):
        return False

    return any(marker in normalized for marker in ("repond", "reponse", "brouillon")) or (
        "redige" in normalized and any(marker in normalized for marker in ("reponse", "recu", "dernier"))
    )


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
    if wants_gmail_reply_draft(message):
        messages = list_gmail_messages(max_results=1)
        if not messages:
            return "Je n'ai trouve aucun mail recent auquel preparer une reponse."

        original = get_gmail_message(messages[0].id)
        examples = find_sent_examples(original.sender_email)

        prompt = f"""
Tu dois rediger un brouillon de reponse email pour Victor.
Ne dis jamais que le mail a ete envoye.
La reponse doit etre prete a relire, modifier et valider par Victor.

Profil local:
{build_profile_prompt_context()}

Instruction de Victor:
{message}

Mail recu:
{format_email_for_prompt(original)}

Exemples de mails deja envoyes par Victor:
{format_sent_examples_for_prompt(examples)}

Donne uniquement:
1. Objet propose;
2. Brouillon du mail;
3. Points a verifier avant envoi.
""".strip()

        try:
            draft = await ask_ollama([{"role": "user", "content": prompt}])
        except OllamaClientError as exc:
            raise GmailIntegrationError(str(exc)) from exc

        return (
            "J'ai prepare un brouillon, sans envoyer le mail.\n\n"
            f"Mail source: {original.subject} ({original.sender})\n\n"
            f"{draft}"
        )

    if force_list or wants_gmail_list(message):
        return format_gmail_message_list()

    return None


def gmail_message_dicts(query: str, max_results: int) -> list[dict[str, str]]:
    return [message_to_dict(message) for message in list_gmail_messages(query, max_results)]

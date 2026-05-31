import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cognition.output_sanitizer import looks_like_internal_dump, sanitize_assistant_output


RAW_TELEGRAM_DUMP = """
Resolver Eva active.
Objectif compris: Lire les mails reels lies au sujet demande.
Diagnostic: l'outil gmail_client n'a pas donne de resultat fiable.
Trace locale: resolver #4

Ce que j'ai deja tente:
- gmail_client: failed - {'error': 'invalid_grant', 'error_description': 'Token has been expired or revoked.'}

Plan de reprise autonome:
- utiliser la recherche web gratuite si l'outil local echoue

Routes alternatives candidates: gmail reply audit, gmail read, gmail reply draft
Etat: aucune route n'a encore donne une preuve suffisante.
"""


def test_internal_resolver_dump_is_hidden() -> None:
    assert looks_like_internal_dump(RAW_TELEGRAM_DUMP)
    cleaned = sanitize_assistant_output(
        RAW_TELEGRAM_DUMP,
        user_message="J'ai des mails concernant DreamLense qui sont a repondre ?",
        channel="telegram",
    )
    assert "Resolver Eva active" not in cleaned
    assert "invalid_grant" not in cleaned
    assert "reconnectee" in cleaned or "reconnecter" in cleaned
    assert "je n'invente pas" in cleaned.lower()


def test_private_mail_web_misroute_is_hidden() -> None:
    cleaned = sanitize_assistant_output(
        "Recherche web gratuite: c'est quoi mes derniers mails auxquels j'ai pas encore repondu",
        user_message="c'est quoi mes derniers mails auxquels j'ai pas encore repondu",
        channel="web",
    )
    assert "Recherche web gratuite" not in cleaned
    assert "Gmail" in cleaned or "mails reels" in cleaned


if __name__ == "__main__":
    test_internal_resolver_dump_is_hidden()
    test_private_mail_web_misroute_is_hidden()
    print("output sanitizer tests OK")

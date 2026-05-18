import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.config import settings
from app.integrations.gmail_client import (
    GMAIL_SCOPES,
    gmail_credentials_path,
    gmail_token_path,
    google_token_scope_status,
)


class GmailAuthLaunchError(Exception):
    """Raised when Eva cannot start the local Gmail OAuth flow."""


BACKEND_DIR = Path(__file__).resolve().parents[2]
_oauth_process: subprocess.Popen[Any] | None = None


def start_gmail_oauth_flow(force_reconnect: bool = False) -> dict[str, object]:
    global _oauth_process

    credentials_file = gmail_credentials_path()
    token_file = gmail_token_path()

    if not settings.eva_gmail_enabled:
        raise GmailAuthLaunchError("Gmail est desactive. Active EVA_GMAIL_ENABLED=true dans backend/.env.")

    if not credentials_file.exists():
        raise GmailAuthLaunchError(
            "Fichier OAuth Gmail absent. Place le JSON Google complet dans data/gmail_credentials.json."
        )

    token_status = google_token_scope_status()
    if token_file.exists() and force_reconnect:
        backup_path = token_file.with_name(f"{token_file.stem}_previous.json")
        if backup_path.exists():
            backup_path.unlink()
        shutil.move(str(token_file), str(backup_path))

    if token_file.exists() and token_status["has_required_scopes"]:
        return {
            "started": False,
            "already_connected": True,
            "requires_user_consent": False,
            "message": "Gmail est deja connecte localement.",
            "token_path": str(token_file),
        }

    if token_file.exists() and not token_status["has_required_scopes"]:
        return {
            "started": False,
            "already_connected": False,
            "requires_user_consent": True,
            "message": (
                "Google est connecte, mais le token local n'a pas tous les scopes requis. "
                "Relance avec force_reconnect=true pour regenerer un token Gmail + Calendar."
            ),
            "token_path": str(token_file),
            "missing_scopes": token_status["missing_scopes"],
        }

    if _oauth_process and _oauth_process.poll() is None:
        return {
            "started": False,
            "already_running": True,
            "requires_user_consent": True,
            "message": "Le flux OAuth Gmail est deja en cours. Termine la validation dans le navigateur.",
        }

    creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    _oauth_process = subprocess.Popen(
        [sys.executable, "-m", "app.integrations.gmail_auth"],
        cwd=str(BACKEND_DIR),
        creationflags=creationflags,
    )

    return {
        "started": True,
        "already_connected": False,
        "requires_user_consent": True,
        "message": (
            "Flux OAuth Gmail lance. Connecte-toi dans la page Google ouverte, "
            "puis reviens dans Eva et rafraichis le panneau Gmail."
        ),
        "token_path": str(token_file),
    }


def main() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise SystemExit(
            "Dependances Gmail absentes. Lance: pip install -r requirements.txt"
        ) from exc

    credentials_file = gmail_credentials_path()
    token_file = gmail_token_path()

    if not credentials_file.exists():
        raise SystemExit(
            f"Fichier OAuth introuvable: {credentials_file}\n"
            "Telecharge le JSON OAuth Google complet et place-le dans data/gmail_credentials.json.\n"
            "Le Client ID seul ne suffit pas: le JSON doit aussi contenir client_secret."
        )

    token_file.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), GMAIL_SCOPES)
    credentials = flow.run_local_server(port=0)
    token_file.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Connexion Gmail OK. Token local ecrit: {token_file}")


if __name__ == "__main__":
    main()

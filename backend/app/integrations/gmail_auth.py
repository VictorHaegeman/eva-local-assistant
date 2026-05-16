from app.integrations.gmail_client import GMAIL_SCOPES, gmail_credentials_path, gmail_token_path


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

import json
import shutil
from pathlib import Path
from typing import Any


class ProfileStoreError(Exception):
    """Raised when Eva cannot safely load the local profile."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
PROFILE_PATH = DATA_DIR / "eva_profile.json"
PROFILE_EXAMPLE_PATH = DATA_DIR / "eva_profile.example.json"

FORBIDDEN_KEY_PARTS = (
    "password",
    "passwd",
    "token",
    "api_key",
    "apikey",
    "secret",
)


def ensure_profile_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if PROFILE_PATH.exists():
        return

    if not PROFILE_EXAMPLE_PATH.exists():
        raise ProfileStoreError(
            f"Le fichier exemple du profil est introuvable: {PROFILE_EXAMPLE_PATH}"
        )

    shutil.copyfile(PROFILE_EXAMPLE_PATH, PROFILE_PATH)


def _find_forbidden_keys(value: Any, path: str = "profile") -> list[str]:
    matches: list[str] = []

    if isinstance(value, dict):
        for key, child_value in value.items():
            normalized_key = str(key).lower()
            child_path = f"{path}.{key}"

            if any(part in normalized_key for part in FORBIDDEN_KEY_PARTS):
                matches.append(child_path)

            matches.extend(_find_forbidden_keys(child_value, child_path))

    if isinstance(value, list):
        for index, child_value in enumerate(value):
            matches.extend(_find_forbidden_keys(child_value, f"{path}[{index}]"))

    return matches


def load_profile() -> dict[str, Any]:
    ensure_profile_file()

    try:
        with PROFILE_PATH.open("r", encoding="utf-8") as profile_file:
            profile = json.load(profile_file)
    except json.JSONDecodeError as exc:
        raise ProfileStoreError(
            "Le profil local data/eva_profile.json contient du JSON invalide."
        ) from exc
    except OSError as exc:
        raise ProfileStoreError("Impossible de lire le profil local Eva.") from exc

    if not isinstance(profile, dict):
        raise ProfileStoreError("Le profil local Eva doit etre un objet JSON.")

    forbidden_keys = _find_forbidden_keys(profile)
    if forbidden_keys:
        joined_keys = ", ".join(forbidden_keys)
        raise ProfileStoreError(
            "Le profil local ne doit pas contenir de mots de passe, tokens, "
            f"cles API ou secrets. Cles interdites trouvees: {joined_keys}"
        )

    return profile


def build_profile_prompt_context() -> str:
    profile = load_profile()

    identity = profile.get("identity", {})
    projects = profile.get("projects", [])
    writing_preferences = profile.get("writing_preferences", {})
    safety_rules = profile.get("safety_rules", [])

    lines = [
        "Profil local de Victor charge depuis data/eva_profile.json.",
        "Utilise ces informations quand elles sont utiles, sans pretendre faire une action reelle.",
    ]

    if isinstance(identity, dict):
        user_name = identity.get("user_name")
        email = identity.get("email")
        if user_name:
            lines.append(f"Nom utilisateur: {user_name}")
        if email:
            lines.append(f"Email utilisateur: {email}")

    if isinstance(projects, list) and projects:
        lines.append("Projets connus:")
        for project in projects:
            if not isinstance(project, dict):
                continue

            project_parts = []
            name = project.get("name")
            description = project.get("description")
            website = project.get("website")
            role = project.get("role")

            if name:
                project_parts.append(str(name))
            if role:
                project_parts.append(f"role: {role}")
            if description:
                project_parts.append(f"description: {description}")
            if website:
                project_parts.append(f"site: {website}")

            if project_parts:
                lines.append(f"- {'; '.join(project_parts)}")

    if isinstance(writing_preferences, dict):
        style = writing_preferences.get("style")
        email_signature = writing_preferences.get("email_signature")
        if style:
            lines.append(f"Preference de redaction: {style}")
        if email_signature:
            lines.append(f"Signature email a utiliser si demande: {email_signature}")

    if isinstance(safety_rules, list) and safety_rules:
        lines.append("Regles de securite du profil:")
        for rule in safety_rules:
            if isinstance(rule, str) and rule.strip():
                lines.append(f"- {rule.strip()}")

    return "\n".join(lines)

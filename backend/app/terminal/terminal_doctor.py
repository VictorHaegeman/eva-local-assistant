import os
import subprocess
from dataclasses import dataclass
from typing import Any

from app.integrations.cli_tools import find_gh


class TerminalDoctorError(Exception):
    """Raised when Eva cannot diagnose or fix a terminal error."""


@dataclass(frozen=True)
class TerminalFix:
    key: str
    label: str
    explanation: str
    command: str
    safe_to_launch: bool


@dataclass(frozen=True)
class TerminalDiagnosis:
    detected: bool
    title: str
    cause: str
    fix: TerminalFix | None
    next_steps: list[str]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def looks_like_terminal_error(text: str) -> bool:
    normalized = _normalize(text)
    markers = (
        "commandnotfoundexception",
        "n'est pas reconnu",
        "not recognized as",
        "fullyqualifiederrorid",
        "categoryinfo",
        "traceback",
        "error:",
        "exception",
        "err_connection_refused",
        "access_denied",
    )
    return any(marker in normalized for marker in markers)


def analyze_terminal_error(error_text: str) -> TerminalDiagnosis:
    text = error_text.strip()
    normalized = _normalize(text)

    if (
        "commandnotfoundexception" in normalized
        and "c:\\program" in normalized
        and "github cli\\gh.exe" in normalized
        and "auth login" in normalized
    ):
        gh = find_gh()
        command = (
            f'& "{gh}" auth login --hostname github.com --git-protocol https --web'
            if gh
            else 'winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements'
        )
        return TerminalDiagnosis(
            detected=True,
            title="Chemin Windows non quote pour GitHub CLI",
            cause=(
                "PowerShell a coupe le chemin au premier espace dans `C:\\Program Files`. "
                "Il essaie donc d'executer `C:\\Program` au lieu de `gh.exe`."
            ),
            fix=TerminalFix(
                key="github_cli_auth_quoted_path",
                label="Relancer GitHub auth avec le chemin correct",
                explanation=(
                    "Eva peut relancer `gh auth login` avec un appel PowerShell correct. "
                    "La validation GitHub reste humaine dans le navigateur."
                ),
                command=command,
                safe_to_launch=bool(gh),
            ),
            next_steps=[
                "Valider la connexion GitHub dans la page ouverte.",
                "Verifier ensuite avec `gh auth status`.",
                "Relancer la demande Project Factory si Eva devait creer un repo.",
            ],
        )

    if "err_connection_refused" in normalized and ("localhost:5173" in normalized or "127.0.0.1:5173" in normalized):
        return TerminalDiagnosis(
            detected=True,
            title="Frontend Eva indisponible",
            cause="Le navigateur ne trouve rien sur le port Vite 5173.",
            fix=TerminalFix(
                key="restart_eva_frontend",
                label="Relancer Eva via start-eva.bat",
                explanation="Eva peut relancer les scripts locaux si le fichier de lancement existe.",
                command="start-eva.bat",
                safe_to_launch=True,
            ),
            next_steps=[
                "Verifier que le backend ecoute sur 8000.",
                "Verifier que le frontend ecoute sur 5173.",
                "Rafraichir http://localhost:5173.",
            ],
        )

    if "cursor-agent" in normalized and ("introuvable" in normalized or "not recognized" in normalized or "not found" in normalized):
        return TerminalDiagnosis(
            detected=True,
            title="cursor-agent absent",
            cause="Cursor Agent CLI n'est pas installe dans l'environnement courant.",
            fix=None,
            next_steps=[
                "Installer WSL avec `wsl --install`.",
                "Apres redemarrage, installer cursor-agent dans WSL.",
                "Relancer Doctor pour verifier `cursor_agent_cli`.",
            ],
        )

    return TerminalDiagnosis(
        detected=looks_like_terminal_error(text),
        title="Erreur terminal non reconnue automatiquement",
        cause=(
            "Eva detecte une erreur, mais aucun correctif local fiable n'est encore code "
            "pour ce motif precis."
        )
        if looks_like_terminal_error(text)
        else "Le texte ne ressemble pas assez a une erreur terminal.",
        fix=None,
        next_steps=[
            "Copier l'erreur complete dans Eva ou Telegram.",
            "Ajouter le contexte: commande lancee, dossier courant, objectif.",
            "Eva peut ensuite proposer un diagnostic ou creer un prompt Cursor.",
        ],
    )


def launch_terminal_fix(fix_key: str) -> dict[str, object]:
    if fix_key == "github_cli_auth_quoted_path":
        gh = find_gh()
        if not gh:
            raise TerminalDoctorError("GitHub CLI gh est introuvable.")

        command = [gh, "auth", "login", "--hostname", "github.com", "--git-protocol", "https", "--web"]
        if os.name == "nt":
            subprocess.Popen(
                command,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen(command)
        return {
            "started": True,
            "message": "GitHub auth relance correctement. Termine la validation dans le navigateur.",
            "command": '& "' + gh + '" auth login --hostname github.com --git-protocol https --web',
        }

    if fix_key == "restart_eva_frontend":
        if os.name != "nt":
            raise TerminalDoctorError("Relance start-eva.bat disponible seulement sur Windows.")
        subprocess.Popen(["cmd", "/c", "start", "", "start-eva.bat"], shell=False)
        return {
            "started": True,
            "message": "Relance Eva demandee via start-eva.bat.",
            "command": "start-eva.bat",
        }

    raise TerminalDoctorError(f"Correctif inconnu: {fix_key}")


def diagnosis_to_dict(diagnosis: TerminalDiagnosis) -> dict[str, Any]:
    return {
        "detected": diagnosis.detected,
        "title": diagnosis.title,
        "cause": diagnosis.cause,
        "fix": None
        if diagnosis.fix is None
        else {
            "key": diagnosis.fix.key,
            "label": diagnosis.fix.label,
            "explanation": diagnosis.fix.explanation,
            "command": diagnosis.fix.command,
            "safe_to_launch": diagnosis.fix.safe_to_launch,
        },
        "next_steps": diagnosis.next_steps,
    }


def format_terminal_diagnosis(diagnosis: TerminalDiagnosis, launched: dict[str, object] | None = None) -> str:
    lines = [
        f"Terminal Doctor: {diagnosis.title}",
        "",
        f"Cause: {diagnosis.cause}",
    ]
    if diagnosis.fix:
        lines.extend(
            [
                "",
                f"Correctif: {diagnosis.fix.label}",
                diagnosis.fix.explanation,
                f"Commande: {diagnosis.fix.command}",
            ]
        )
    if launched:
        lines.extend(["", f"Action lancee: {launched.get('message')}"])
    lines.append("")
    lines.append("Prochaines etapes:")
    lines.extend(f"- {step}" for step in diagnosis.next_steps)
    return "\n".join(lines)

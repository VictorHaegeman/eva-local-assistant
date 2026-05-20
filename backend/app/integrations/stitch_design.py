import re
import unicodedata
from dataclasses import dataclass

from app.config import settings
from app.integrations.browser import open_url
from app.integrations.desktop_automation import DesktopAutomationError, set_clipboard_text


class StitchDesignError(Exception):
    """Raised when Eva cannot prepare a Google Stitch design workflow."""


@dataclass(frozen=True)
class StitchDesignPackage:
    prompt: str
    opened_url: str
    copied_to_clipboard: bool


STITCH_MARKERS = (
    "stitch",
    "google stitch",
    "maquette",
    "wireframe",
    "design frontend",
    "design front",
    "design ui",
    "ui design",
    "interface frontend",
    "interface front",
    "ecran d'app",
    "écran d'app",
    "ecrans d'app",
    "écrans d'app",
)

FRONTEND_BUILD_MARKERS = (
    "frontend",
    "front-end",
    "react",
    "vite",
    "site",
    "app web",
    "interface",
    "dashboard",
    "landing",
)


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def wants_stitch_design(message: str) -> bool:
    normalized = _normalize(message)
    explicit = any(marker in normalized for marker in STITCH_MARKERS)
    if explicit:
        return True

    asks_design = any(
        marker in normalized
        for marker in (
            "fais un design",
            "prepare un design",
            "cree un design",
            "genere un design",
            "propose une interface",
            "refais l'interface",
            "refait l'interface",
            "optimise le design",
        )
    )
    frontend_context = any(marker in normalized for marker in FRONTEND_BUILD_MARKERS)
    return asks_design and frontend_context


def build_stitch_prompt(
    request: str,
    project_name: str = "Projet frontend",
    design_direction: str = "",
) -> str:
    clean_request = " ".join(request.strip().split())
    clean_project = " ".join(project_name.strip().split()) or "Projet frontend"
    direction = " ".join(design_direction.strip().split())
    if not direction:
        direction = (
            "interface web moderne, premium, sobre, responsive, avec une DA sombre "
            "bleu/cyan, structure claire et composants directement implementables en React"
        )

    return f"""
Create a production-ready frontend design for:
{clean_project}

User request:
{clean_request}

Design direction:
{direction}

Target:
- React + Vite implementation
- desktop and mobile responsive screens
- premium assistant/product quality
- clear navigation, strong hierarchy, polished spacing
- real app screens, not a generic marketing mockup unless explicitly requested

Required output:
1. Generate the main screens and important states.
2. Keep the design practical for implementation.
3. Include component names, layout structure and design tokens.
4. Prefer restrained dark UI with blue/cyan highlights, not green.
5. Avoid decorative clutter, nested cards and unreadable text.
6. Make primary workflows obvious and usable.
7. Export or provide a DESIGN.md / implementation notes that Cursor can use.

Important constraints:
- No paid API dependency.
- No OpenAI dependency.
- No secrets, tokens or private data in the design.
- Design must be adaptable to local-first apps.
""".strip()


def prepare_stitch_design(
    request: str,
    project_name: str = "Projet frontend",
    design_direction: str = "",
    open_in_browser: bool = True,
) -> StitchDesignPackage:
    if not settings.eva_stitch_enabled:
        raise StitchDesignError("Google Stitch bridge desactive. Active EVA_STITCH_ENABLED=true.")

    prompt = build_stitch_prompt(
        request=request,
        project_name=project_name,
        design_direction=design_direction,
    )

    copied = False
    try:
        set_clipboard_text(prompt)
        copied = True
    except DesktopAutomationError as exc:
        raise StitchDesignError(f"Impossible de copier le prompt Stitch: {exc}") from exc

    opened_url = ""
    if open_in_browser and settings.eva_stitch_auto_open_browser:
        opened_url = settings.eva_stitch_url
        open_url(opened_url)

    return StitchDesignPackage(
        prompt=prompt,
        opened_url=opened_url,
        copied_to_clipboard=copied,
    )


def format_stitch_design_response(package: StitchDesignPackage) -> str:
    lines = [
        "Google Stitch bridge pret.",
        f"Prompt copie dans le presse-papiers: {'oui' if package.copied_to_clipboard else 'non'}",
    ]
    if package.opened_url:
        lines.append(f"Stitch ouvert dans Brave: {package.opened_url}")
    else:
        lines.append("Stitch non ouvert automatiquement.")
    lines.extend(
        [
            "",
            "Workflow conseille:",
            "1. Colle le prompt dans Stitch.",
            "2. Genere la maquette.",
            "3. Exporte ou copie DESIGN.md / les notes de design.",
            "4. Donne ces notes a Eva/Cursor pour coder le frontend.",
        ]
    )
    return "\n".join(lines)


def stitch_prompt_file_content(request: str, project_name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", project_name.strip()).strip("-") or "project"
    return (
        f"# Google Stitch Design Prompt - {project_name}\n\n"
        "Ce fichier est genere par Eva pour preparer une maquette frontend dans Google Stitch.\n\n"
        f"Projet: `{slug}`\n\n"
        "## Prompt a coller dans Stitch\n\n"
        "```text\n"
        f"{build_stitch_prompt(request=request, project_name=project_name)}\n"
        "```\n\n"
        "## Utilisation avec Cursor\n\n"
        "1. Genere la maquette dans Stitch.\n"
        "2. Exporte/copie les notes `DESIGN.md` si disponibles.\n"
        "3. Ajoute-les au projet avant de demander a Cursor de coder.\n"
        "4. Cursor doit respecter la maquette, mais garder le code simple et maintenable.\n"
    )

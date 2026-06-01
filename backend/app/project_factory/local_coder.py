import json
import re
from pathlib import Path
from typing import Any

from app.config import settings


class LocalProjectCoderError(Exception):
    """Raised when Eva cannot generate a local project V1 safely."""


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _projects_root() -> Path:
    configured = Path(settings.eva_projects_dir).expanduser()
    if configured.is_absolute():
        return configured.resolve()
    return (PROJECT_ROOT / configured).resolve()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", value.strip().lower()).strip("-")
    return slug or "eva-project"


def _pascal_case(value: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", value)
    candidate = "".join(part[:1].upper() + part[1:] for part in parts)
    return candidate or "EvaProject"


def _js_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _workspace_from_plan(plan: dict[str, Any], *, allow_outside_projects_dir: bool) -> Path:
    raw_path = str(plan.get("workspace_path", "")).strip()
    if not raw_path:
        raise LocalProjectCoderError("workspace_path manquant dans le plan projet.")

    workspace = Path(raw_path).expanduser().resolve()
    if not workspace.name:
        raise LocalProjectCoderError("Chemin workspace invalide.")

    if not allow_outside_projects_dir:
        root = _projects_root()
        try:
            workspace.relative_to(root)
        except ValueError as exc:
            raise LocalProjectCoderError(
                f"Workspace hors dossier projets autorise: {workspace}"
            ) from exc

    return workspace


def _safe_write(
    workspace: Path,
    relative_path: str,
    content: str,
    *,
    force: bool,
) -> tuple[str, str]:
    relative = Path(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise LocalProjectCoderError(f"Chemin fichier refuse: {relative_path}")

    target = (workspace / relative).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise LocalProjectCoderError(f"Chemin fichier refuse: {relative_path}") from exc

    if target.exists() and not force:
        existing = target.read_text(encoding="utf-8", errors="replace")
        generated_scaffold = any(
            marker in existing
            for marker in (
                "Projet prepare par Eva.",
                "A completer apres generation du projet",
                "Construire une premiere version utilisable",
            )
        )
        replaceable = relative.as_posix() in {
            "README.md",
            "PROJECT_BRIEF.md",
            "TASKS.md",
            ".gitignore",
        }
        if not (replaceable and generated_scaffold):
            return relative.as_posix(), "skipped"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return relative.as_posix(), "written"


def _feature_ideas(idea: str) -> list[str]:
    normalized = idea.lower()
    features = [
        "Tableau de bord clair pour piloter le projet",
        "Workflow simple pour transformer une idee en action",
        "Architecture locale, gratuite et facile a faire evoluer",
    ]
    if any(word in normalized for word in ("saas", "prospect", "client", "crm")):
        features[0] = "Suivi des prospects, opportunites et prochaines actions"
        features[1] = "Vue pipeline pour prioriser les relances"
    if any(word in normalized for word in ("f1", "formule", "race", "course")):
        features[0] = "Dashboard de donnees et resultats de course"
        features[1] = "Hypotheses ML et indicateurs de performance"
    if any(word in normalized for word in ("dreamlense", "portrait", "linkedin")):
        features[0] = "Idees de contenus et actions commerciales DreamLense"
        features[1] = "Generation de briefs et posts a partir du contexte local"
    return features


def _web_v1_files(project_name: str, slug: str, idea: str, stack: dict[str, str]) -> dict[str, str]:
    features = _feature_ideas(idea)
    app_title = _js_string(project_name)
    feature_array = ",\n  ".join(_js_string(feature) for feature in features)
    api_name = _pascal_case(slug)

    return {
        "README.md": f"""# {project_name}

V1 codee localement par Eva Project Factory.

## Idee

{idea}

## Stack

- Frontend: {stack.get("frontend", "React + Vite")}
- Backend: {stack.get("backend", "Python FastAPI")}
- Modele IA: aucun service cloud obligatoire

## Lancer en local

Backend:

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

Ouvre ensuite http://localhost:5173.

## Verification V1

- Le backend expose `/api/health`.
- Le frontend charge le statut backend.
- Les fichiers sont prets pour Cursor/Codex si tu veux continuer.
""",
        "PROJECT_BRIEF.md": f"""# Project Brief - {project_name}

## Objectif

Construire une V1 utilisable a partir de l'idee suivante:

> {idea}

## Fonctionnalites V1

- Interface web propre et responsive.
- API locale minimale.
- Composants faciles a remplacer.
- Pas de dependance payante obligatoire.

## Contraintes

- Secrets hors Git.
- Code lisible.
- Architecture simple.
""",
        "TASKS.md": """# Tasks

- [x] Creer le squelette V1 local
- [x] Ajouter un frontend React/Vite
- [x] Ajouter un backend FastAPI
- [ ] Installer les dependances
- [ ] Lancer backend et frontend
- [ ] Ajouter les vraies donnees metier
- [ ] Faire auditer le code par Cursor/Codex
""",
        ".gitignore": """node_modules/
dist/
build/
.env
.env.*
!.env.example
.venv/
venv/
__pycache__/
*.pyc
.DS_Store
Thumbs.db
""",
        "package.json": """{
  "scripts": {
    "dev:frontend": "npm --prefix frontend run dev -- --host 0.0.0.0",
    "dev:backend": "cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
  }
}
""",
        "backend/requirements.txt": """fastapi==0.115.6
uvicorn[standard]==0.34.0
python-dotenv==1.0.1
""",
        "backend/.env.example": f"""APP_NAME={project_name}
CORS_ORIGINS=*
""",
        "backend/app/__init__.py": "",
        "backend/app/main.py": f'''from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="{api_name}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BriefRequest(BaseModel):
    note: str = ""


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {{"status": "ok", "project": "{project_name}"}}


@app.get("/api/items")
async def items() -> dict[str, object]:
    return {{
        "items": [
            {{"label": "{features[0]}", "status": "ready"}},
            {{"label": "{features[1]}", "status": "draft"}},
            {{"label": "{features[2]}", "status": "planned"}},
        ]
    }}


@app.post("/api/brief")
async def brief(request: BriefRequest) -> dict[str, object]:
    return {{
        "summary": "Brief local prepare.",
        "input": request.note,
        "next_steps": [
            "Verifier le scope V1",
            "Connecter les donnees reelles",
            "Ajouter les tests essentiels",
        ],
    }}
''',
        "frontend/package.json": """{
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@vitejs/plugin-react": "latest",
    "vite": "latest",
    "react": "latest",
    "react-dom": "latest",
    "lucide-react": "latest"
  },
  "devDependencies": {}
}
""",
        "frontend/index.html": """<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Eva Project V1</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/App.jsx"></script>
  </body>
</html>
""",
        "frontend/vite.config.js": """import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
""",
        "frontend/src/App.jsx": f'''import {{ useEffect, useMemo, useState }} from "react";
import {{ Activity, ArrowUpRight, CheckCircle2, Sparkles }} from "lucide-react";
import "./styles.css";

const projectName = {app_title};
const features = [
  {feature_array}
];

export default function App() {{
  const [health, setHealth] = useState("sync");
  const [items, setItems] = useState([]);

  useEffect(() => {{
    fetch("/api/health")
      .then((response) => response.json())
      .then(() => setHealth("online"))
      .catch(() => setHealth("offline"));

    fetch("/api/items")
      .then((response) => response.json())
      .then((payload) => setItems(payload.items || []))
      .catch(() => setItems([]));
  }}, []);

  const cards = useMemo(() => items.length ? items : features.map((label) => ({{ label, status: "draft" }})), [items]);

  return (
    <main className="shell">
      <section className="hero">
        <div className="orb" aria-hidden="true">
          <span />
        </div>
        <div className="hero-copy">
          <p className="eyebrow">V1 locale</p>
          <h1>{{projectName}}</h1>
          <p className="lead">
            Prototype genere par Eva pour transformer l'idee en produit testable.
          </p>
          <div className="actions">
            <a href="#workspace">
              Ouvrir le workspace <ArrowUpRight size={{18}} />
            </a>
            <span className={{`status ${{health}}`}}>
              <Activity size={{16}} /> {{health}}
            </span>
          </div>
        </div>
      </section>

      <section id="workspace" className="grid">
        {{cards.map((item) => (
          <article className="panel" key={{item.label}}>
            <CheckCircle2 size={{22}} />
            <h2>{{item.label}}</h2>
            <p>{{item.status}}</p>
          </article>
        ))}}
      </section>

      <section className="brief">
        <Sparkles size={{20}} />
        <div>
          <h2>Prochaine iteration</h2>
          <p>Connecter les donnees reelles, ajouter les tests et demander a Cursor/Codex d'etendre la V1.</p>
        </div>
      </section>
    </main>
  );
}}
''',
        "frontend/src/styles.css": """* {
  box-sizing: border-box;
}

:root {
  color: #eaf7ff;
  background: #04080d;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

body {
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(circle at 30% 20%, rgba(74, 191, 255, 0.2), transparent 32rem),
    linear-gradient(135deg, #03070d 0%, #081622 55%, #03070d 100%);
}

.shell {
  width: min(1120px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 64px 0;
}

.hero {
  display: grid;
  grid-template-columns: minmax(260px, 420px) 1fr;
  gap: 56px;
  align-items: center;
  min-height: 68vh;
}

.orb {
  aspect-ratio: 1;
  border: 1px solid rgba(93, 210, 255, 0.42);
  border-radius: 999px;
  position: relative;
  display: grid;
  place-items: center;
  background:
    radial-gradient(circle, rgba(111, 219, 255, 0.38), transparent 36%),
    linear-gradient(145deg, rgba(16, 55, 80, 0.75), rgba(2, 8, 14, 0.2));
  box-shadow: 0 0 70px rgba(75, 191, 255, 0.22);
  overflow: hidden;
}

.orb::before,
.orb::after {
  content: "";
  position: absolute;
  inset: 12%;
  border-radius: inherit;
  border: 1px dashed rgba(129, 219, 255, 0.5);
  animation: spin 18s linear infinite;
}

.orb::after {
  inset: 26%;
  animation-duration: 11s;
  animation-direction: reverse;
}

.orb span {
  width: 38%;
  aspect-ratio: 1;
  border-radius: inherit;
  background: rgba(104, 212, 255, 0.18);
  box-shadow: inset 0 0 32px rgba(255, 255, 255, 0.16), 0 0 34px rgba(102, 205, 255, 0.35);
}

.eyebrow {
  margin: 0 0 12px;
  color: #68d8ff;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: clamp(48px, 8vw, 104px);
  line-height: 0.95;
}

.lead {
  color: #aac0d4;
  font-size: 20px;
  line-height: 1.6;
  max-width: 620px;
}

.actions {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  align-items: center;
}

.actions a,
.status {
  min-height: 48px;
  border: 1px solid rgba(111, 210, 255, 0.35);
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  color: #eaf7ff;
  text-decoration: none;
  background: rgba(13, 31, 45, 0.78);
}

.status.online {
  border-color: rgba(84, 255, 194, 0.5);
}

.status.offline {
  border-color: rgba(255, 107, 107, 0.5);
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.panel,
.brief {
  border: 1px solid rgba(111, 210, 255, 0.22);
  border-radius: 8px;
  background: rgba(8, 23, 35, 0.82);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.24);
}

.panel {
  min-height: 180px;
  padding: 24px;
}

.panel svg,
.brief svg {
  color: #68d8ff;
}

.panel h2 {
  font-size: 22px;
  line-height: 1.25;
}

.panel p,
.brief p {
  color: #9fb5c8;
}

.brief {
  display: flex;
  gap: 16px;
  margin-top: 16px;
  padding: 24px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 820px) {
  .hero {
    grid-template-columns: 1fr;
    gap: 32px;
  }

  .orb {
    max-width: 360px;
    margin: 0 auto;
  }

  .grid {
    grid-template-columns: 1fr;
  }
}
""",
    }


def _python_cli_files(project_name: str, slug: str, idea: str, stack: dict[str, str]) -> dict[str, str]:
    package_name = re.sub(r"[^a-zA-Z0-9_]+", "_", slug.replace("-", "_")).strip("_") or "eva_project"
    return {
        "README.md": f"""# {project_name}

V1 CLI codee localement par Eva Project Factory.

## Idee

{idea}

## Lancement

```powershell
python -m venv .venv
.\\.venv\\Scripts\\activate
pip install -e .
{package_name} --help
```
""",
        "PROJECT_BRIEF.md": f"# Project Brief - {project_name}\n\n{idea}\n",
        "TASKS.md": "# Tasks\n\n- [x] Creer la CLI V1\n- [ ] Ajouter la logique metier\n- [ ] Ajouter des tests\n",
        ".gitignore": ".env\n.venv/\n__pycache__/\n*.pyc\n.DS_Store\nThumbs.db\n",
        "pyproject.toml": f"""[project]
name = "{slug}"
version = "0.1.0"
description = "V1 locale generee par Eva"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
{package_name} = "{package_name}.main:main"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
""",
        f"src/{package_name}/__init__.py": "__version__ = '0.1.0'\n",
        f"src/{package_name}/main.py": f'''import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="{project_name}")
    parser.add_argument("--note", default="", help="Note de travail a traiter")
    args = parser.parse_args()

    print("{project_name} est pret.")
    if args.note:
        print(f"Note recue: {{args.note}}")


if __name__ == "__main__":
    main()
''',
        "tests/test_smoke.py": f"""from {package_name}.main import main


def test_main_exists():
    assert callable(main)
""",
    }


def build_local_v1_files(plan: dict[str, Any]) -> dict[str, str]:
    project_name = str(plan.get("project_name") or "Nouveau Projet").strip() or "Nouveau Projet"
    slug = str(plan.get("slug") or _slugify(project_name))
    idea = str(plan.get("idea") or "Projet prepare par Eva.").strip()
    stack = plan.get("stack") if isinstance(plan.get("stack"), dict) else {}
    template = str(stack.get("template") or "saas-mvp").strip().lower()

    if template == "python-cli":
        return _python_cli_files(project_name, slug, idea, {str(k): str(v) for k, v in stack.items()})
    return _web_v1_files(project_name, slug, idea, {str(k): str(v) for k, v in stack.items()})


def generate_local_v1(
    plan: dict[str, Any],
    *,
    force: bool = False,
    allow_outside_projects_dir: bool = False,
) -> dict[str, Any]:
    workspace = _workspace_from_plan(plan, allow_outside_projects_dir=allow_outside_projects_dir)
    files = build_local_v1_files(plan)
    workspace.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    skipped: list[str] = []
    for relative_path, content in files.items():
        path, status = _safe_write(workspace, relative_path, content, force=force)
        if status == "written":
            written.append(path)
        else:
            skipped.append(path)

    return {
        "workspace_path": str(workspace),
        "project_name": str(plan.get("project_name") or workspace.name),
        "template": str((plan.get("stack") or {}).get("template", "saas-mvp"))
        if isinstance(plan.get("stack"), dict)
        else "saas-mvp",
        "written": written,
        "skipped": skipped,
        "written_count": len(written),
        "skipped_count": len(skipped),
    }

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.project_factory.agent_runner import audit_project_workspace
from app.project_factory.local_coder import generate_local_v1


def _plan(workspace: Path) -> dict[str, object]:
    return {
        "project_name": "Test SaaS",
        "slug": "test-saas",
        "workspace_path": str(workspace),
        "repo_name": "test-saas",
        "idea": "Une app SaaS pour suivre des prospects et les prochaines actions.",
        "stack": {
            "template": "saas-mvp",
            "frontend": "React + Vite",
            "backend": "Python FastAPI",
            "notes": "Test local.",
        },
    }


def test_local_coder_generates_runnable_web_v1() -> None:
    with TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir) / "test-saas"
        result = generate_local_v1(
            _plan(workspace),
            force=True,
            allow_outside_projects_dir=True,
        )

        assert result["written_count"] >= 10
        assert (workspace / "README.md").exists()
        assert (workspace / "frontend" / "src" / "App.jsx").exists()
        assert (workspace / "frontend" / "src" / "styles.css").exists()
        assert (workspace / "backend" / "app" / "main.py").exists()
        assert "A completer apres generation" not in (workspace / "README.md").read_text(encoding="utf-8")

        audit = audit_project_workspace(workspace)
        assert audit["status"] in {"pass", "warning"}
        assert audit["implementation_file_count"] >= 5


def test_local_coder_does_not_overwrite_without_force() -> None:
    with TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir) / "test-saas"
        plan = _plan(workspace)
        generate_local_v1(plan, force=True, allow_outside_projects_dir=True)
        readme = workspace / "README.md"
        readme.write_text("custom", encoding="utf-8")

        result = generate_local_v1(plan, force=False, allow_outside_projects_dir=True)

        assert result["skipped_count"] > 0
        assert readme.read_text(encoding="utf-8") == "custom"


def test_local_coder_replaces_eva_scaffold_readme_without_force() -> None:
    with TemporaryDirectory() as tmp_dir:
        workspace = Path(tmp_dir) / "test-saas"
        workspace.mkdir(parents=True)
        readme = workspace / "README.md"
        readme.write_text(
            "# Test SaaS\n\nProjet prepare par Eva.\n\nA completer apres generation du projet.\n",
            encoding="utf-8",
        )

        result = generate_local_v1(
            _plan(workspace),
            force=False,
            allow_outside_projects_dir=True,
        )

        assert "README.md" in result["written"]
        assert "V1 codee localement" in readme.read_text(encoding="utf-8")


if __name__ == "__main__":
    test_local_coder_generates_runnable_web_v1()
    test_local_coder_does_not_overwrite_without_force()
    test_local_coder_replaces_eva_scaffold_readme_without_force()
    print("project factory local coder OK")

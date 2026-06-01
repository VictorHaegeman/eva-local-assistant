import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.roles import build_roles_prompt_context, select_roles


def _keys(message: str, mode: str = "chat") -> set[str]:
    return {role.key for role, _ in select_roles(message, mode)}


def test_project_request_selects_project_roles() -> None:
    keys = _keys("ouvre le projet F1 dans Cursor et donne un prompt a Codex", "code")

    assert "ceo_orchestrator" in keys
    assert "project_architect" in keys
    assert "code_operator" in keys


def test_email_request_selects_account_role() -> None:
    keys = _keys("lis mon dernier mail DreamLense et prepare une reponse", "chat")

    assert "ceo_orchestrator" in keys
    assert "account_executive" in keys


def test_roles_prompt_is_hidden_operational_context() -> None:
    prompt = build_roles_prompt_context("fais un post LinkedIn pour DreamLense", "dreamlense")

    assert "CMO" in prompt
    assert "ne les decris pas a Victor" in prompt

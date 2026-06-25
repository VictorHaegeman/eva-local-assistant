import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.board.boardroom as boardroom
import app.board.ceo as ceo_mod
import app.board.cfo as cfo_mod
import app.board.cto as cto_mod
from app.board.ceo import CeoBrief
from app.board.cfo import CfoVerdict
from app.board.cto import CtoPlan
from app.llm.ollama_client import OllamaClientError


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


def _async_raise(exc):
    async def _inner(*args, **kwargs):
        raise exc
    return _inner


# --- CEO -------------------------------------------------------------------

def test_ceo_parses_trivial(monkeypatch) -> None:
    monkeypatch.setattr(ceo_mod, "build_board_officer_context", lambda *a, **k: "")
    monkeypatch.setattr(
        ceo_mod,
        "ask_ollama_json",
        _async_return(
            {
                "objective": "dire bonjour",
                "complexity": "trivial",
                "needs_cto": False,
                "needs_cfo": False,
                "direct_answer": "Salut Victor.",
            }
        ),
    )
    brief = asyncio.run(ceo_mod.deliberate_ceo("salut"))
    assert brief.is_trivial
    assert brief.direct_answer == "Salut Victor."


def test_ceo_fallback_on_brain_error(monkeypatch) -> None:
    monkeypatch.setattr(ceo_mod, "build_board_officer_context", lambda *a, **k: "")
    monkeypatch.setattr(ceo_mod, "ask_ollama_json", _async_raise(OllamaClientError("down")))
    brief = asyncio.run(ceo_mod.deliberate_ceo("fais un truc complexe"))
    assert brief.complexity == "standard"
    assert brief.needs_cto and brief.needs_cfo


# --- CFO --------------------------------------------------------------------

def test_cfo_block_verdict(monkeypatch) -> None:
    monkeypatch.setattr(cfo_mod, "build_board_officer_context", lambda *a, **k: "")
    monkeypatch.setattr(
        cfo_mod,
        "ask_ollama_json",
        _async_return(
            {
                "verdict": "bloquer",
                "risk_level": "eleve",
                "reversible": False,
                "requires_confirmation": True,
                "reason": "envoi externe non valide",
            }
        ),
    )
    verdict = asyncio.run(cfo_mod.deliberate_cfo("obj", "envoie un mail a tout le monde"))
    assert verdict.blocks
    assert verdict.requires_confirmation


def test_cfo_fallback_requires_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(cfo_mod, "build_board_officer_context", lambda *a, **k: "")
    monkeypatch.setattr(cfo_mod, "ask_ollama_json", _async_raise(OllamaClientError("down")))
    verdict = asyncio.run(cfo_mod.deliberate_cfo("obj", "supprime des fichiers"))
    assert verdict.requires_confirmation is True


# --- Boardroom orchestration ------------------------------------------------

def test_board_short_circuits_on_trivial(monkeypatch) -> None:
    monkeypatch.setattr(boardroom, "append_board_decision", lambda *a, **k: True)
    monkeypatch.setattr(
        boardroom,
        "deliberate_ceo",
        _async_return(
            CeoBrief(
                objective="dire bonjour",
                complexity="trivial",
                needs_cto=False,
                needs_cfo=False,
                direct_answer="Salut.",
            )
        ),
    )
    result = asyncio.run(boardroom.run_board_deliberation("salut"))
    assert result.is_direct
    assert result.direct_answer == "Salut."
    assert [stage["label"] for stage in result.trace["stages"]] == ["CEO"]


def test_board_runs_all_officers_and_flags_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(boardroom, "append_board_decision", lambda *a, **k: True)
    monkeypatch.setattr(
        boardroom,
        "deliberate_ceo",
        _async_return(
            CeoBrief(
                objective="publier un post",
                complexity="complexe",
                needs_cto=True,
                needs_cfo=True,
                direct_answer="",
            )
        ),
    )
    monkeypatch.setattr(
        boardroom,
        "deliberate_cto",
        _async_return(CtoPlan(approach="ouvrir LinkedIn", steps=("rediger", "ouvrir"), feasible=True)),
    )
    monkeypatch.setattr(
        boardroom,
        "deliberate_cfo",
        _async_return(
            CfoVerdict(
                verdict="prudence",
                risk_level="moyen",
                requires_confirmation=True,
                reason="publication externe",
            )
        ),
    )
    result = asyncio.run(boardroom.run_board_deliberation("publie ce post sur LinkedIn"))
    assert not result.is_direct
    assert result.requires_confirmation
    assert "CFO" in result.confirmation_note or "validation" in result.confirmation_note.lower()
    assert [stage["label"] for stage in result.trace["stages"]] == ["CEO", "CTO", "CFO"]
    assert "Deliberation du board" in result.deliberation_context


def test_board_runs_coo_and_gates_execution_on_cfo(monkeypatch) -> None:
    from app.board.coo import CooPlan

    monkeypatch.setattr(boardroom, "append_board_decision", lambda *a, **k: True)
    monkeypatch.setattr(
        boardroom,
        "deliberate_ceo",
        _async_return(
            CeoBrief(
                objective="ranger le bureau",
                complexity="standard",
                needs_cto=True,
                needs_cfo=True,
                direct_answer="",
                needs_coo=True,
            )
        ),
    )
    monkeypatch.setattr(boardroom, "deliberate_cto", _async_return(CtoPlan(approach="lister puis trier", feasible=True)))
    # CFO bloque -> le COO ne doit pas etre lance du tout.
    monkeypatch.setattr(
        boardroom,
        "deliberate_cfo",
        _async_return(CfoVerdict(verdict="bloquer", risk_level="eleve", requires_confirmation=True, reason="suppression")),
    )

    captured = {}

    async def _fake_coo(objective, message, plan_summary="", cfo_clearance=True):
        captured["called"] = True
        return CooPlan(next_action="x", execute_now=cfo_clearance)

    monkeypatch.setattr(boardroom, "deliberate_coo", _fake_coo)
    result = asyncio.run(boardroom.run_board_deliberation("supprime tout le dossier"))
    assert "called" not in captured  # CFO blocking skips the COO
    assert result.requires_confirmation
    assert [stage["label"] for stage in result.trace["stages"]] == ["CEO", "CTO", "CFO"]


def test_board_coo_runs_when_cfo_allows(monkeypatch) -> None:
    from app.board.coo import CooPlan

    monkeypatch.setattr(boardroom, "append_board_decision", lambda *a, **k: True)
    monkeypatch.setattr(
        boardroom,
        "deliberate_ceo",
        _async_return(
            CeoBrief(
                objective="ouvrir une recherche",
                complexity="standard",
                needs_cto=True,
                needs_cfo=True,
                direct_answer="",
                needs_coo=True,
            )
        ),
    )
    monkeypatch.setattr(boardroom, "deliberate_cto", _async_return(CtoPlan(approach="chercher", feasible=True)))
    monkeypatch.setattr(boardroom, "deliberate_cfo", _async_return(CfoVerdict(verdict="go", risk_level="faible")))

    async def _fake_coo(objective, message, plan_summary="", cfo_clearance=True):
        return CooPlan(next_action="lancer la recherche web", execute_now=cfo_clearance, owner="web_search")

    monkeypatch.setattr(boardroom, "deliberate_coo", _fake_coo)
    result = asyncio.run(boardroom.run_board_deliberation("cherche le meilleur vol"))
    labels = [stage["label"] for stage in result.trace["stages"]]
    assert labels == ["CEO", "CTO", "CFO", "COO"]
    assert "COO / prochaine action" in result.deliberation_context


def test_board_enabled_resolution(monkeypatch) -> None:
    monkeypatch.setattr(boardroom, "settings", SimpleNamespace(eva_board_enabled="true"))
    assert boardroom.board_enabled() is True
    monkeypatch.setattr(boardroom, "settings", SimpleNamespace(eva_board_enabled="false"))
    assert boardroom.board_enabled() is False
    monkeypatch.setattr(boardroom, "settings", SimpleNamespace(eva_board_enabled="auto"))
    monkeypatch.setattr(boardroom, "resolve_provider", lambda: "groq")
    assert boardroom.board_enabled() is True
    monkeypatch.setattr(boardroom, "resolve_provider", lambda: "ollama")
    assert boardroom.board_enabled() is False

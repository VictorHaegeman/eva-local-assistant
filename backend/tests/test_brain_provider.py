import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.llm.brain as brain


def _fake_settings(monkeypatch, **kwargs) -> None:
    defaults = {
        "eva_brain_provider": "auto",
        "groq_api_key": "",
        "groq_model": "llama-3.3-70b-versatile",
        "groq_reasoning_model": "llama-3.3-70b-versatile",
        "ollama_model": "llama3.1:8b",
        "ollama_reasoning_model": "llama3.1:8b",
    }
    defaults.update(kwargs)
    monkeypatch.setattr(brain, "settings", SimpleNamespace(**defaults))


def test_auto_uses_ollama_without_key(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="auto", groq_api_key="")
    assert brain.resolve_provider() == "ollama"


def test_auto_uses_groq_with_key(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="auto", groq_api_key="gsk_test")
    assert brain.resolve_provider() == "groq"


def test_forced_groq_falls_back_to_ollama_without_key(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="groq", groq_api_key="")
    assert brain.resolve_provider() == "ollama"


def test_forced_ollama_ignores_key(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="ollama", groq_api_key="gsk_test")
    assert brain.resolve_provider() == "ollama"


def test_model_for_tier_groq(monkeypatch) -> None:
    _fake_settings(
        monkeypatch,
        groq_model="llama-3.3-70b-versatile",
        groq_reasoning_model="reasoner-x",
    )
    assert brain.model_for_tier("chat", "groq") == "llama-3.3-70b-versatile"
    assert brain.model_for_tier("reasoning", "groq") == "reasoner-x"


def test_model_for_tier_ollama(monkeypatch) -> None:
    _fake_settings(
        monkeypatch,
        ollama_model="llama3.1:8b",
        ollama_reasoning_model="reason:8b",
    )
    assert brain.model_for_tier("chat", "ollama") == "llama3.1:8b"
    assert brain.model_for_tier("reasoning", "ollama") == "reason:8b"

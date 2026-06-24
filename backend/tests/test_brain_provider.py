import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.llm.brain as brain


def _fake_settings(monkeypatch, **kwargs) -> None:
    defaults = {
        "eva_brain_provider": "auto",
        "groq_api_key": "",
        "groq_base_url": "https://api.groq.com/openai/v1",
        "groq_model": "",
        "groq_reasoning_model": "",
        "openrouter_api_key": "",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openrouter_model": "",
        "openrouter_reasoning_model": "",
        "gemini_api_key": "",
        "gemini_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini_model": "",
        "gemini_reasoning_model": "",
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


def test_auto_priority_groq_over_openrouter(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="auto", groq_api_key="g", openrouter_api_key="o")
    assert brain.resolve_provider() == "groq"


def test_auto_falls_to_openrouter_then_gemini(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="auto", openrouter_api_key="o")
    assert brain.resolve_provider() == "openrouter"
    _fake_settings(monkeypatch, eva_brain_provider="auto", gemini_api_key="g")
    assert brain.resolve_provider() == "gemini"


def test_forced_openrouter_without_key_falls_back(monkeypatch) -> None:
    _fake_settings(monkeypatch, eva_brain_provider="openrouter", openrouter_api_key="")
    assert brain.resolve_provider() == "ollama"


def test_model_for_tier_uses_configured_or_fallback(monkeypatch) -> None:
    _fake_settings(monkeypatch, groq_model="", groq_reasoning_model="custom-reason")
    # Vide -> premier modele connu-bon (auto-reparation).
    assert brain.model_for_tier("chat", "groq") == brain.PROVIDER_FALLBACK_MODELS["groq"][0]
    # Configure -> respecte le choix.
    assert brain.model_for_tier("reasoning", "groq") == "custom-reason"


def test_candidate_models_starts_with_requested_then_fallbacks() -> None:
    candidates = brain._candidate_models("groq", "openai/gpt-oss-20b")
    assert candidates[0] == "openai/gpt-oss-20b"
    # Les autres modeles connus suivent, sans doublon.
    assert "openai/gpt-oss-120b" in candidates
    assert len(candidates) == len(set(candidates))


def test_model_for_tier_ollama(monkeypatch) -> None:
    _fake_settings(
        monkeypatch,
        ollama_model="llama3.1:8b",
        ollama_reasoning_model="reason:8b",
    )
    assert brain.model_for_tier("chat", "ollama") == "llama3.1:8b"
    assert brain.model_for_tier("reasoning", "ollama") == "reason:8b"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.curiosity.curiosity_loop import DEFAULT_FOCUS, _score_item


def test_curiosity_scores_relevant_business_ai_content() -> None:
    score, tags = _score_item(
        "AI agents for LinkedIn prospecting",
        "Autonomous automation can help small businesses qualify leads and draft posts.",
        "business",
        list(DEFAULT_FOCUS),
    )

    assert score >= 18
    assert "ai" in tags
    assert "linkedin" in tags


def test_curiosity_keeps_generic_noise_low() -> None:
    score, tags = _score_item(
        "Weather forecast",
        "A generic daily update with rain and temperature information.",
        "general",
        list(DEFAULT_FOCUS),
    )

    assert score < 10
    assert tags == ()

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.curiosity.curiosity_loop import _configured_wikipedia_topics, _score_item


def test_curiosity_config_uses_targeted_wikipedia_topics() -> None:
    topics = _configured_wikipedia_topics(
        {
            "wikipedia": {
                "topics": [
                    {
                        "title": "Reinforcement learning",
                        "language": "en",
                        "category": "machine_learning",
                        "priority": 34,
                        "reason": "bonus/malus Eva",
                    }
                ]
            }
        }
    )

    assert topics[0].title == "Reinforcement learning"
    assert topics[0].category == "machine_learning"
    assert topics[0].priority == 34


def test_curiosity_scoring_rewards_victor_focus() -> None:
    score, tags = _score_item(
        "Autonomous AI agent for business productivity",
        "A local agent uses memory and automation to improve decisions.",
        "ai",
        ["IA", "agents autonomes", "business", "productivite"],
    )

    assert score >= 15
    assert "ai" in tags
    assert "business" in tags


def test_curiosity_keeps_generic_noise_low() -> None:
    score, tags = _score_item(
        "Weather forecast",
        "A generic daily update with rain and temperature information.",
        "general",
        ["IA", "agents autonomes", "business", "productivite"],
    )

    assert score < 10
    assert tags == ()


if __name__ == "__main__":
    test_curiosity_config_uses_targeted_wikipedia_topics()
    test_curiosity_scoring_rewards_victor_focus()
    test_curiosity_keeps_generic_noise_low()
    print("curiosity loop tests OK")

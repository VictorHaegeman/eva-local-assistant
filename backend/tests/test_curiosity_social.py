import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.curiosity.curiosity_loop import (
    _configured_social_profiles,
    _configured_social_queries,
    _extract_x_public_profile_text,
    _score_item,
)


def test_social_public_queries_are_configurable() -> None:
    config = {
        "social_public": {
            "enabled": True,
            "queries": [
                {
                    "query": 'site:x.com "AI agents"',
                    "category": "social_ai_agents",
                    "priority": 31,
                    "reason": "tester les signaux sociaux",
                }
            ],
        }
    }
    queries = _configured_social_queries(config)
    assert len(queries) == 1
    assert queries[0].query == 'site:x.com "AI agents"'
    assert queries[0].category == "social_ai_agents"
    assert queries[0].priority == 31


def test_social_public_signals_score_social_patterns() -> None:
    score, tags = _score_item(
        "AI agents workflow hook on X",
        "A public Twitter/X signal about builders sharing local AI automation and growth hooks.",
        "social_ai_agents",
        ["Twitter", "agents autonomes", "creator economy"],
    )
    assert score > 0
    assert "twitter" in tags
    assert "social" in tags or "creator economy" in tags


def test_social_public_profiles_are_configurable() -> None:
    config = {
        "social_public": {
            "enabled": True,
            "profiles": [
                {
                    "handle": "OpenAI",
                    "url": "https://x.com/OpenAI",
                    "category": "social_ai_profile",
                    "priority": 18,
                    "reason": "observer un profil IA",
                }
            ],
        }
    }
    profiles = _configured_social_profiles(config)
    assert len(profiles) == 1
    assert profiles[0].handle == "OpenAI"
    assert profiles[0].url == "https://x.com/OpenAI"


def test_social_public_profile_extractor_reads_public_metadata() -> None:
    html = (
        '{"name":"OpenAI","screen_name":"OpenAI",'
        '"description":"OpenAI builds useful AI systems for everyone.",'
        '"followers_count":123456}'
    )
    extracted = _extract_x_public_profile_text(html)
    assert "OpenAI" in extracted
    assert "useful AI systems" in extracted
    assert "123456" in extracted


if __name__ == "__main__":
    test_social_public_queries_are_configurable()
    test_social_public_signals_score_social_patterns()
    test_social_public_profiles_are_configurable()
    test_social_public_profile_extractor_reads_public_metadata()
    print("curiosity social tests OK")

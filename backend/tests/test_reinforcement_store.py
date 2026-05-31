import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cognition.reinforcement_store import feedback_reward_from_message, reward_from_tick_fields


def test_completed_tick_gets_positive_reward() -> None:
    reward, reason = reward_from_tick_fields(
        status="completed",
        message="ouvre une carte de Londres",
        response="Carte ouverte dans Brave.",
        domain="browser",
        route="browser_or_video",
    )
    assert reward > 0
    assert "completed" in reason


def test_gmail_misroute_to_web_gets_penalty() -> None:
    reward, reason = reward_from_tick_fields(
        status="completed",
        message="c'est quoi mes derniers mails auxquels j'ai pas encore repondu",
        response="Recherche web gratuite: comment trouver les mails non repondus dans Gmail.",
        domain="gmail",
        route="web_search",
    )
    assert reward < 0
    assert "wrong_web_fallback" in reason


def test_negative_feedback_gets_penalty() -> None:
    reward, reason = reward_from_tick_fields(
        status="needs_followup",
        message="Elle comprends rien, c'est pas normal.",
        response="Je peux ouvrir Cursor mais il me manque le projet cible.",
        domain="cursor",
        route="cursor_work",
    )
    assert reward <= -1.0
    assert "negative_feedback" in reason


def test_positive_feedback_gets_bonus() -> None:
    reward, reason = reward_from_tick_fields(
        status="completed",
        message="Nickel, exactement ca marche.",
        response="Action effectuee.",
        domain="desktop",
        route="desktop_control",
    )
    assert reward >= 1.0
    assert "positive_feedback" in reason


def test_explicit_feedback_parser_targets_previous_tick() -> None:
    parsed = feedback_reward_from_message("C'est pas normal, elle comprend rien.")
    assert parsed is not None
    reward, reason = parsed
    assert reward < 0
    assert reason == "explicit_negative_feedback"


if __name__ == "__main__":
    test_completed_tick_gets_positive_reward()
    test_gmail_misroute_to_web_gets_penalty()
    test_negative_feedback_gets_penalty()
    test_positive_feedback_gets_bonus()
    test_explicit_feedback_parser_targets_previous_tick()
    print("reinforcement store tests OK")

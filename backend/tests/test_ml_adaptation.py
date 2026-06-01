import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.understanding import build_understanding_frame
from app.cognition.ml_adaptation import (
    build_ml_adaptation_context,
    ml_adaptation_status,
    rank_routes_with_ml_policy,
)


def _frame(message: str):
    return build_understanding_frame(
        message,
        conversation_context=[],
        trusted_actions=True,
    )


def test_ml_policy_keeps_gmail_before_web_for_private_mail_request() -> None:
    message = "c'est quoi mes derniers mails auxquels j'ai pas encore repondu"
    frame = _frame(message)

    ranked = rank_routes_with_ml_policy(
        ["web_search", "gmail_reply_audit", "generic_chat"],
        frame,
        message,
    )

    assert ranked[0] == "gmail_reply_audit"
    assert ranked[-1] == "web_search"


def test_ml_context_explains_active_lessons_for_current_state() -> None:
    message = "ouvre le projet de machine learning sur la F1"
    frame = _frame(message)

    context = build_ml_adaptation_context(message, frame)

    assert "Adaptation ML locale active" in context
    assert "KNN/cas proches" in context
    assert f"Etat ML: {frame.primary_domain}:{frame.expected_outcome}" in context


def test_ml_adaptation_status_exposes_course_adapters() -> None:
    status = ml_adaptation_status(limit=5)
    courses = {lesson["course"] for lesson in status["lessons"]}

    assert status["enabled"] is True
    assert {"KNN", "Metrics evaluation", "Cross-validation", "Training process"} <= courses

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.understanding import build_understanding_frame


def _frame(message: str, context: list[dict[str, str]] | None = None):
    return build_understanding_frame(
        message,
        conversation_context=context or [],
        trusted_actions=True,
    )


def test_dreamlense_mail_draft_routes_to_gmail() -> None:
    frame = _frame(
        "lis mon derniers mail concernant dreamlense et ouvre le moi "
        "et prepare une reponse base sur mes reponses passees"
    )
    assert frame.primary_domain == "gmail"
    assert frame.expected_outcome == "draft"
    assert frame.action_plan.route == "gmail_reply_draft"


def test_gmail_followup_does_not_become_cursor() -> None:
    context = [
        {
            "role": "user",
            "content": (
                "lis mon derniers mail concernant dreamlense et ouvre le moi "
                "et prepare une reponse base sur mes reponses passees"
            ),
        },
        {
            "role": "assistant",
            "content": "Source: Gmail API + brouillon Gmail. Mail source: DreamLense.",
        },
    ]
    frame = _frame("ouvre le dans brave et prepare une reponse prete a etre envoye", context)
    assert frame.primary_domain == "gmail"
    assert frame.expected_outcome == "draft"
    assert frame.action_plan.route == "gmail_reply_draft"


def test_reponse_does_not_match_repo() -> None:
    frame = _frame("prepare une reponse claire et courte")
    assert frame.action_plan.route != "cursor_work"


if __name__ == "__main__":
    test_dreamlense_mail_draft_routes_to_gmail()
    test_gmail_followup_does_not_become_cursor()
    test_reponse_does_not_match_repo()
    print("understanding regressions OK")

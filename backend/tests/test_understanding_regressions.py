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


def test_linkedin_post_routes_to_linkedin_operator() -> None:
    frame = _frame("Fais un post LinkedIn pertinent pour DreamLense et ouvre LinkedIn.")
    assert frame.primary_domain == "linkedin"
    assert frame.expected_outcome == "draft"
    assert frame.action_plan.route == "linkedin_browser_post"


def test_news_does_not_reuse_linkedin_context() -> None:
    context = [
        {
            "role": "user",
            "content": "Fais un post LinkedIn pertinent pour DreamLense et ouvre LinkedIn.",
        },
        {
            "role": "assistant",
            "content": "Post LinkedIn prepare dans le compositeur.",
        },
    ]
    frame = _frame("des news", context)
    assert frame.primary_domain == "web"
    assert frame.expected_outcome == "search"
    assert frame.action_plan.route == "web_search"


if __name__ == "__main__":
    test_dreamlense_mail_draft_routes_to_gmail()
    test_gmail_followup_does_not_become_cursor()
    test_reponse_does_not_match_repo()
    test_linkedin_post_routes_to_linkedin_operator()
    test_news_does_not_reuse_linkedin_context()
    print("understanding regressions OK")

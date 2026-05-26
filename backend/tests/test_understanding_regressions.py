import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.understanding import build_understanding_frame
from app.cognition.critic import criticize_response
from app.cognition.problem_solver import diagnose_problem, problem_routes_for_result
from app.cognition.tool_result import ToolResult
from app.integrations.beeper_assistant import beeper_response_has_useful_content


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


def test_linkedin_activity_does_not_create_post() -> None:
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
    frame = _frame("et des activites sur mon compte linkedin ?", context)
    assert frame.primary_domain == "linkedin"
    assert frame.expected_outcome == "read_then_summarize"
    assert frame.action_plan.route == "linkedin_activity"


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


def test_new_project_idea_routes_to_project_factory() -> None:
    frame = _frame("j'ai une nouvelle idee de projet: une app SaaS pour suivre mes prospects")
    assert frame.primary_domain == "project"
    assert frame.expected_outcome == "create_workspace"
    assert frame.action_plan.route == "project_factory"


def test_create_app_routes_to_project_factory_before_browser() -> None:
    frame = _frame("cree une app web pour visualiser mes ventes et lance le projet")
    assert frame.primary_domain == "project"
    assert frame.action_plan.route == "project_factory"


def test_future_action_claim_is_not_success() -> None:
    report = criticize_response(
        "Je vais essayer de naviguer sur LinkedIn directement pour voir les messages non repondu.",
        [ToolResult(tool="beeper_assistant", status="success", evidence=("Beeper ouvert.",), confidence=0.7)],
        requires_action=True,
    )
    assert not report.passed
    assert report.retryable


def test_beeper_unverified_response_is_not_useful() -> None:
    assert not beeper_response_has_useful_content(
        "Source: Beeper desktop/web + lecture pixels locale.\n"
        "Beeper visible: non\n"
        "Je n'ai pas obtenu de lecture Beeper fiable."
    )


def test_problem_solver_turns_browser_failure_into_web_fallback() -> None:
    frame = _frame("ouvre une carte de Londres")
    result = ToolResult(
        tool="browser_assistant",
        status="failed",
        error="Aucune destination navigateur fiable n'a ete detectee.",
    )
    routes = problem_routes_for_result(result, frame, trusted_actions=True)
    assert "web_search" in routes


def test_problem_solver_permission_block_keeps_safe_fallback() -> None:
    frame = _frame("ouvre Spotify sur mon PC")
    result = ToolResult(
        tool="spotify_assistant",
        status="blocked",
        error="Cette action locale demande une session fiable: PC local ou Telegram autorise.",
    )
    resolution = diagnose_problem(result, frame, trusted_actions=False)
    assert resolution.problem_type == "permission"
    assert resolution.blocked_by_policy
    assert problem_routes_for_result(result, frame, trusted_actions=False) == ("web_search",)


if __name__ == "__main__":
    test_dreamlense_mail_draft_routes_to_gmail()
    test_gmail_followup_does_not_become_cursor()
    test_reponse_does_not_match_repo()
    test_linkedin_post_routes_to_linkedin_operator()
    test_linkedin_activity_does_not_create_post()
    test_news_does_not_reuse_linkedin_context()
    test_new_project_idea_routes_to_project_factory()
    test_create_app_routes_to_project_factory_before_browser()
    test_future_action_claim_is_not_success()
    test_beeper_unverified_response_is_not_useful()
    test_problem_solver_turns_browser_failure_into_web_fallback()
    test_problem_solver_permission_block_keeps_safe_fallback()
    print("understanding regressions OK")

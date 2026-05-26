import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.understanding import build_understanding_frame
from app.cognition.critic import criticize_response
from app.cognition.problem_solver import (
    build_direct_problem_solver_response,
    build_exception_recovery_response,
    diagnose_problem,
    problem_routes_for_result,
)
from app.cognition.structured_interpreter import StructuredInterpretation, _should_accept_interpretation
from app.cognition.tool_result import ToolResult
from app.integrations.beeper_assistant import beeper_response_has_useful_content
from app.integrations.cursor_agent_setup import format_cursor_agent_setup_response
from app.projects.project_chat import attach_recent_project_context, infer_project_resolution


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


def test_f1_project_work_routes_to_cursor_before_browser() -> None:
    frame = _frame(
        "Je veux que tu continue de travailler sur le projet de F1, ouvre le et donne "
        "des prompts a cursor ou alors code toi meme dans le projet pour optimiser "
        "la partie site web du projet"
    )
    assert frame.primary_domain == "cursor"
    assert frame.action_plan.route == "cursor_work"


def test_cursor_followup_resolves_project_from_recent_context() -> None:
    context_focus = (
        "Victor: Je veux que tu continues de travailler sur le projet de F1. "
        "Eva: Je suppose que tu parles de neural-network-F1. "
        "Session Cursor preparee pour neural-network-F1."
    )
    contextual_message = attach_recent_project_context(
        "Vas-y donne le prompt a cursor et ouvre cursor pour lui le donner",
        context_focus,
    )
    resolution = infer_project_resolution(contextual_message)
    assert resolution is not None
    assert resolution.project["name"] == "neural-network-F1"


def test_cursor_agent_install_routes_to_setup_not_project() -> None:
    frame = _frame("Installe cursor agent pour tous les projets")
    assert frame.primary_domain == "cursor"
    assert frame.expected_outcome == "execute_local"
    assert frame.action_plan.route == "cursor_agent_setup"


def test_cursor_agent_setup_cannot_be_overridden_to_project_work() -> None:
    frame = _frame("Installe cursor-agent pour tous les projets")
    interpretation = StructuredInterpretation(
        goal="Preparer une session Cursor",
        domain="cursor",
        outcome="prepare_prompt",
        route="cursor_work",
        confidence=0.99,
        should_execute=True,
        needs_clarification=False,
        clarification_question="",
        reasoning_summary="Mauvaise route simulee.",
        candidate_routes=("cursor_work",),
        risk_level="local_action",
        evidence_required=("projet cible",),
    )
    assert not _should_accept_interpretation(interpretation, frame)


def test_cursor_agent_setup_formatter_keeps_blocked_diagnostic_useful() -> None:
    response = format_cursor_agent_setup_response(
        {
            "status": "blocked",
            "before": {"wsl_available": False},
            "after": {"installed": False},
            "install": {
                "attempted": False,
                "success": False,
                "message": "WSL indisponible.",
            },
        }
    )
    assert "Cursor Agent setup." in response
    assert "curl https://cursor.com/install -fsS | bash" in response
    assert "cursor-agent --version" in response


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


def test_direct_problem_solver_replaces_permission_refusal() -> None:
    frame = _frame("lis mon ecran et corrige l'erreur visible")
    response = build_direct_problem_solver_response(
        "lis mon ecran et corrige l'erreur visible",
        frame,
        tool="screen_reader",
        reason="Lecture ecran depuis un canal non fiable.",
        trusted_actions=False,
        next_actions=("relancer depuis Telegram autorise",),
    )
    assert response.startswith("Mode resolution active.")
    assert "Eva ne peut pas" not in response


def test_exception_recovery_does_not_end_as_raw_error() -> None:
    response = build_exception_recovery_response(
        "ouvre mon projet F1",
        "Projet introuvable",
    )
    assert response.startswith("Mode resolution active.")
    assert "Eva ne peut pas repondre" not in response


if __name__ == "__main__":
    test_dreamlense_mail_draft_routes_to_gmail()
    test_gmail_followup_does_not_become_cursor()
    test_reponse_does_not_match_repo()
    test_linkedin_post_routes_to_linkedin_operator()
    test_linkedin_activity_does_not_create_post()
    test_news_does_not_reuse_linkedin_context()
    test_new_project_idea_routes_to_project_factory()
    test_f1_project_work_routes_to_cursor_before_browser()
    test_cursor_followup_resolves_project_from_recent_context()
    test_cursor_agent_install_routes_to_setup_not_project()
    test_cursor_agent_setup_cannot_be_overridden_to_project_work()
    test_cursor_agent_setup_formatter_keeps_blocked_diagnostic_useful()
    test_create_app_routes_to_project_factory_before_browser()
    test_future_action_claim_is_not_success()
    test_beeper_unverified_response_is_not_useful()
    test_problem_solver_turns_browser_failure_into_web_fallback()
    test_problem_solver_permission_block_keeps_safe_fallback()
    test_direct_problem_solver_replaces_permission_refusal()
    test_exception_recovery_does_not_end_as_raw_error()
    print("understanding regressions OK")

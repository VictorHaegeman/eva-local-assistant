import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.understanding import build_understanding_frame
from app.screen.training_autopilot import (
    looks_like_blocked_assessment_request,
    wants_training_autopilot,
)


def test_project_voltaire_training_detected() -> None:
    assert wants_training_autopilot(
        "J'ai un entrainement Projet Voltaire a faire, continue les exercices visibles"
    )


def test_training_request_routes_to_screen_not_code_project() -> None:
    frame = build_understanding_frame(
        "Projet Voltaire: fais les exercices visibles en mode entrainement",
        trusted_actions=True,
    )
    assert frame.primary_domain == "screen"
    assert frame.action_plan.route == "screen_read"
    assert "entrainement visuel" in frame.interpreted_goal


def test_official_assessment_is_blocked_without_training_marker() -> None:
    assert looks_like_blocked_assessment_request(
        "Fais mon examen officiel Projet Voltaire et clique les reponses"
    )


def test_non_official_training_marker_allows_request() -> None:
    assert not looks_like_blocked_assessment_request(
        "C'est un entrainement non officiel Projet Voltaire"
    )


if __name__ == "__main__":
    test_project_voltaire_training_detected()
    test_training_request_routes_to_screen_not_code_project()
    test_official_assessment_is_blocked_without_training_marker()
    test_non_official_training_marker_allows_request()
    print("screen training autopilot tests OK")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import app.memory.operating_rules_store as rules


@pytest.fixture(autouse=True)
def _temp_rules_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(rules, "RULES_PATH", tmp_path / "eva_operating_rules.json")


def test_add_and_list_rule() -> None:
    rule = rules.add_operating_rule("Reponds toujours en francais et de facon courte.")
    listed = rules.list_operating_rules()
    assert any(item.id == rule.id for item in listed)
    assert listed[0].text.startswith("Reponds toujours")


def test_duplicate_rule_is_not_added_twice() -> None:
    rules.add_operating_rule("Toujours verifier avant d'agir.")
    rules.add_operating_rule("toujours   verifier  avant d'agir.")
    assert len(rules.list_operating_rules()) == 1


def test_rule_rejects_secret() -> None:
    with pytest.raises(rules.OperatingRulesError):
        rules.add_operating_rule("Mon api key est sk-test-123456")


def test_remove_rule() -> None:
    rule = rules.add_operating_rule("Eviter les questions inutiles en fin de reponse.")
    assert rules.remove_operating_rule(rule.id) is True
    assert rules.remove_operating_rule(rule.id) is False
    assert rules.list_operating_rules() == []


def test_prompt_context_marks_rules_non_negotiable() -> None:
    assert rules.build_operating_rules_prompt_context() == ""
    rules.add_operating_rule("Utiliser Brave pour ouvrir les pages web.")
    context = rules.build_operating_rules_prompt_context()
    assert "REGLES PERMANENTES" in context
    assert "non negociables" in context
    assert "Brave" in context


def test_detect_rule_command_slash() -> None:
    assert rules.detect_operating_rule_command("/regle reponds court") == "reponds court"
    assert rules.detect_operating_rule_command("/rule answer briefly") == "answer briefly"


def test_detect_rule_command_natural() -> None:
    assert (
        rules.detect_operating_rule_command("retiens cette regle: toujours citer la source")
        == "toujours citer la source"
    )


def test_detect_rule_command_none_for_plain_message() -> None:
    assert rules.detect_operating_rule_command("salut eva, quoi de neuf ?") is None

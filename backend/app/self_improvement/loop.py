import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.agents.operator_journal import OperatorJournalError, record_operator_tick
from app.config import settings
from app.integrations.cursor_bridge import CursorBridgeError, prepare_cursor_work_session
from app.memory.memory_reflector import reflect_message_into_memory_candidate
from app.memory.memory_store import Memory, MemoryStoreError, add_memory, memory_to_dict
from app.memory.obsidian_store import ObsidianMemoryError, mirror_memory_to_obsidian
from app.projects.task_store import ProjectTask, TaskStoreError, create_task, task_to_dict


SelfImproveTarget = Literal["memory", "skill", "code", "mixed"]


class SelfImproveError(Exception):
    """Raised when Eva cannot prepare a self improvement loop."""


@dataclass(frozen=True)
class SelfImprovePlan:
    target: SelfImproveTarget
    confidence: float
    summary: str
    rationale: str
    should_save_memory: bool
    should_create_task: bool
    should_prepare_cursor_prompt: bool
    should_launch_agent: bool
    suggested_tests: tuple[str, ...]


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
SELF_IMPROVE_LOG_PATH = DATA_DIR / "eva_self_improvements.jsonl"
SELF_IMPROVE_PROMPT_PATH = PROJECT_ROOT / "EVA_SELF_IMPROVE_PROMPT.md"


SELF_IMPROVE_MARKERS = (
    "dorenavant",
    "a partir de maintenant",
    "desormais",
    "eva doit",
    "eva devra",
    "je veux que eva",
    "fais en sorte que eva",
    "il faut que eva",
    "corrige ton comportement",
    "corrige-toi",
    "ameliore toi",
    "self-improve",
    "self improvement",
    "ne me reponds jamais",
    "ne reponds jamais",
)


MEMORY_MARKERS = (
    "retiens",
    "souviens",
    "memorise",
    "memoire",
    "apprends",
    "retienne",
    "souviens-toi",
    "dorenavant",
    "a partir de maintenant",
    "desormais",
)


SKILL_MARKERS = (
    "skill",
    "competence",
    "extension",
    "outil",
    "tools",
    "capacite",
    "module",
)


CODE_MARKERS = (
    "code",
    "backend",
    "frontend",
    "route",
    "endpoint",
    "api",
    "bug",
    "corrige",
    "implemente",
    "ajoute",
    "modifie",
    "interface",
    "telegram",
    "gmail",
    "cursor",
    "agent",
    "pixels",
    "ecran",
    "autonomie",
)


def _normalize(text: str) -> str:
    # Windows terminals sometimes pass UTF-8 text as mojibake; normalize both forms.
    replacements = {
        "Ã©": "é",
        "Ã¨": "è",
        "Ãª": "ê",
        "Ã ": "à",
        "Ã´": "ô",
        "Ã»": "û",
        "Ã§": "ç",
        "Ã‰": "É",
    }
    for broken, fixed in replacements.items():
        text = text.replace(broken, fixed)
    text = re.sub(r"dor\W{1,3}navant", "dorenavant", text, flags=re.IGNORECASE)
    text = re.sub(r"m\W{1,3}moire", "memoire", text, flags=re.IGNORECASE)
    text = re.sub(r"am\W{1,3}liore", "ameliore", text, flags=re.IGNORECASE)
    text = re.sub(r"comp\W{1,3}tence", "competence", text, flags=re.IGNORECASE)
    text = re.sub(r"capacit\W{1,3}", "capacite", text, flags=re.IGNORECASE)
    text = re.sub(r"\W{1,3}cran", "ecran", text, flags=re.IGNORECASE)
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _clean_message(message: str) -> str:
    return " ".join(message.strip().split())


def detect_self_improvement_request(message: str) -> bool:
    text = _normalize(message)
    if any(marker in text for marker in tuple(_normalize(marker) for marker in SELF_IMPROVE_MARKERS)):
        return True

    return "eva" in text and any(
        marker in text
        for marker in (
            "ne reflechit pas",
            "comprenne mieux",
            "interprete mieux",
            "avant de repondre",
            "avant d agir",
            "ne fais plus",
            "fais plutot",
        )
    )


def _classify_target(message: str) -> SelfImproveTarget:
    text = _normalize(message)
    has_memory = any(_normalize(marker) in text for marker in MEMORY_MARKERS)
    has_skill = any(_normalize(marker) in text for marker in SKILL_MARKERS)
    has_code = any(_normalize(marker) in text for marker in CODE_MARKERS)

    if has_code and has_skill:
        return "mixed"
    if has_code:
        return "code"
    if has_skill:
        return "skill"
    if has_memory:
        return "memory"
    return "mixed" if "eva" in text else "memory"


def _summary_from_message(message: str) -> str:
    cleaned = _clean_message(message)
    prefixes = (
        r"^\s*eva[, ]*",
        r"^\s*dorenavant[, ]*",
        r"^\s*a partir de maintenant[, ]*",
    )
    summary = cleaned
    for pattern in prefixes:
        summary = re.sub(pattern, "", summary, flags=re.IGNORECASE)
    return summary[:260].strip(" .") or cleaned[:260]


def _build_rule_content(message: str) -> str:
    candidate = reflect_message_into_memory_candidate(message)
    if candidate:
        return candidate.content

    summary = _summary_from_message(message)
    if "eva" not in _normalize(summary):
        return f"Preference de Victor: {summary}"
    return f"Regle de comportement Eva: {summary}"


def build_self_improvement_plan(
    message: str,
    *,
    source: str = "chat",
    auto_launch_agent: bool | None = None,
) -> SelfImprovePlan:
    target = _classify_target(message)
    summary = _summary_from_message(message)
    wants_agent = auto_launch_agent
    if wants_agent is None:
        wants_agent = settings.eva_self_improve_auto_cursor_agent

    should_prepare_cursor = target in {"skill", "code", "mixed"}
    should_create_task = target in {"skill", "code", "mixed"}
    should_save_memory = target in {"memory", "mixed"}
    should_launch_agent = bool(wants_agent and should_prepare_cursor)

    if target == "memory":
        suggested_tests = ("Verifier que la memoire apparait dans GET /memory.",)
        confidence = 0.82
        rationale = "La demande ressemble surtout a une regle ou preference durable."
    elif target == "skill":
        suggested_tests = (
            "Verifier GET /skills.",
            "Tester une demande qui declenche la nouvelle skill.",
        )
        confidence = 0.74
        rationale = "La demande parle d'une capacite/skill a structurer."
    elif target == "code":
        suggested_tests = (
            "python -m compileall backend/app",
            "Tester la route ou le chat concerne.",
        )
        confidence = 0.78
        rationale = "La demande implique une modification de comportement dans le code."
    else:
        suggested_tests = (
            "python -m compileall backend/app",
            "Tester le scenario depuis le chat local et Telegram.",
        )
        confidence = 0.7
        rationale = "La demande combine apprentissage durable et changement technique."

    return SelfImprovePlan(
        target=target,
        confidence=confidence,
        summary=summary,
        rationale=f"{rationale} Source: {source}.",
        should_save_memory=should_save_memory,
        should_create_task=should_create_task,
        should_prepare_cursor_prompt=should_prepare_cursor,
        should_launch_agent=should_launch_agent,
        suggested_tests=suggested_tests,
    )


def _build_cursor_prompt(message: str, plan: SelfImprovePlan, memory_rule: str = "") -> str:
    tests = "\n".join(f"- {test}" for test in plan.suggested_tests)
    memory_section = f"\nRegle memoire proposee:\n{memory_rule}\n" if memory_rule else ""
    return f"""
Tu travailles dans le repo Eva Local Assistant.

Objectif Self Improvement:
{plan.summary}

Demande originale de Victor:
{_clean_message(message)}

Classification Eva:
- cible: {plan.target}
- confiance: {round(plan.confidence * 100)}%
- raison: {plan.rationale}
{memory_section}
Contraintes:
- Garde Eva gratuite et locale.
- N'ajoute pas OpenAI, cloud payant, secret ou token dans le code.
- Ne casse pas l'architecture existante.
- Si l'amelioration touche des actions sensibles, garde les garde-fous existants.
- Les donnees locales doivent rester dans data/ et ignorees par Git.

Travail attendu:
1. Lis les modules existants avant modification.
2. Implemente le plus petit changement robuste.
3. Ajoute ou adapte les checks utiles.
4. Documente le comportement dans README si necessaire.
5. Termine avec un resume clair des fichiers modifies et des tests lances.

Tests attendus:
{tests}
""".strip()


def _write_prompt_file(prompt: str) -> str:
    SELF_IMPROVE_PROMPT_PATH.write_text(
        "# Prompt Eva Self Improvement\n\n"
        "Ce fichier est genere localement par Eva pour ameliorer son propre comportement.\n\n"
        "```text\n"
        f"{prompt}\n"
        "```\n",
        encoding="utf-8",
    )
    return str(SELF_IMPROVE_PROMPT_PATH)


def _append_log(payload: dict[str, object]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "created_at": datetime.now(UTC).isoformat(),
        **payload,
    }
    with SELF_IMPROVE_LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")


def list_self_improvement_events(limit: int = 30) -> list[dict[str, object]]:
    if not SELF_IMPROVE_LOG_PATH.exists():
        return []

    events: list[dict[str, object]] = []
    with SELF_IMPROVE_LOG_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                events.append(payload)
    safe_limit = min(max(limit, 1), 200)
    return events[-safe_limit:][::-1]


def _maybe_mirror_memory(memory: Memory) -> None:
    try:
        mirror_memory_to_obsidian(memory)
    except ObsidianMemoryError:
        pass


def _task_title(plan: SelfImprovePlan) -> str:
    prefix = {
        "memory": "Memoire Eva",
        "skill": "Skill Eva",
        "code": "Code Eva",
        "mixed": "Self-improvement Eva",
    }[plan.target]
    return f"{prefix}: {plan.summary[:90]}"


def execute_self_improvement_loop(
    message: str,
    *,
    source: str = "chat",
    trusted_actions: bool = False,
    auto_launch_agent: bool | None = None,
) -> dict[str, Any]:
    if not settings.eva_self_improve_enabled:
        raise SelfImproveError("Self Improvement Loop desactive dans .env.")
    if not trusted_actions:
        raise SelfImproveError("Self Improvement demande une session locale ou Telegram autorise.")

    plan = build_self_improvement_plan(
        message,
        source=source,
        auto_launch_agent=auto_launch_agent,
    )

    saved_memory = None
    memory_rule = ""
    if plan.should_save_memory:
        try:
            memory_rule = _build_rule_content(message)
            memory = add_memory(
                memory_rule,
                category="operating_rule",
                source="self_improve",
                confidence=0.9,
            )
            _maybe_mirror_memory(memory)
            saved_memory = memory_to_dict(memory)
        except MemoryStoreError as exc:
            raise SelfImproveError(str(exc)) from exc

    task = None
    if plan.should_create_task:
        try:
            task = create_task(
                project=settings.eva_self_improve_project_name,
                title=_task_title(plan),
                description=(
                    f"Source: {source}. Demande: {_clean_message(message)}. "
                    f"Cible: {plan.target}. Raison: {plan.rationale}"
                ),
                priority="high" if plan.target in {"code", "mixed"} else "normal",
            )
        except TaskStoreError as exc:
            raise SelfImproveError(str(exc)) from exc

    prompt = ""
    prompt_file = ""
    cursor_session: dict[str, object] | None = None
    if plan.should_prepare_cursor_prompt:
        prompt = _build_cursor_prompt(message, plan, memory_rule=memory_rule)
        prompt_file = _write_prompt_file(prompt)

        if plan.should_launch_agent:
            try:
                cursor_session = prepare_cursor_work_session(
                    settings.eva_self_improve_project_name,
                    prompt,
                )
            except CursorBridgeError as exc:
                cursor_session = {
                    "cursor_agent": {
                        "available": False,
                        "started": False,
                        "message": str(exc),
                    }
                }

    result: dict[str, Any] = {
        "plan": self_improvement_plan_to_dict(plan),
        "saved_memory": saved_memory,
        "task": task_to_dict(task) if isinstance(task, ProjectTask) else None,
        "prompt": prompt,
        "prompt_file": prompt_file,
        "cursor_session": cursor_session,
    }
    _append_log(
        {
            "source": source,
            "message": _clean_message(message),
            "plan": result["plan"],
            "saved_memory_id": saved_memory.get("id") if isinstance(saved_memory, dict) else None,
            "task_id": task.id if isinstance(task, ProjectTask) else None,
            "prompt_file": prompt_file,
            "cursor_agent": (
                cursor_session.get("cursor_agent")
                if isinstance(cursor_session, dict)
                else None
            ),
        }
    )

    try:
        record_operator_tick(
            f"Self-improve: {_clean_message(message)}",
            format_self_improvement_response(result),
            channel=f"self_improve:{source}",
            trusted_actions=trusted_actions,
            conversation_context=[],
        )
    except OperatorJournalError:
        pass

    return result


def self_improvement_plan_to_dict(plan: SelfImprovePlan) -> dict[str, object]:
    return {
        "target": plan.target,
        "confidence": plan.confidence,
        "summary": plan.summary,
        "rationale": plan.rationale,
        "should_save_memory": plan.should_save_memory,
        "should_create_task": plan.should_create_task,
        "should_prepare_cursor_prompt": plan.should_prepare_cursor_prompt,
        "should_launch_agent": plan.should_launch_agent,
        "suggested_tests": list(plan.suggested_tests),
    }


def format_self_improvement_response(result: dict[str, Any]) -> str:
    plan = result["plan"]
    lines = [
        "Self Improvement Loop lance.",
        f"Cible: {plan['target']} ({round(float(plan['confidence']) * 100)}%).",
        f"Resume: {plan['summary']}",
    ]

    saved_memory = result.get("saved_memory")
    if isinstance(saved_memory, dict):
        lines.append(f"Memoire ajoutee: #{saved_memory.get('id')} [{saved_memory.get('category')}]")

    task = result.get("task")
    if isinstance(task, dict):
        lines.append(f"Tache creee: #{task.get('id')} [{task.get('project')}] {task.get('title')}")

    prompt_file = str(result.get("prompt_file") or "")
    if prompt_file:
        lines.append(f"Prompt Cursor genere: {prompt_file}")

    cursor_session = result.get("cursor_session")
    if isinstance(cursor_session, dict):
        agent = cursor_session.get("cursor_agent")
        if isinstance(agent, dict):
            if agent.get("started"):
                lines.append(f"cursor-agent lance: {agent.get('log_path')}")
            elif agent.get("available") is False:
                lines.append(f"cursor-agent non lance: {agent.get('message')}")

    tests = plan.get("suggested_tests", [])
    if isinstance(tests, list) and tests:
        lines.append("Tests conseilles:")
        lines.extend(f"- {test}" for test in tests)

    lines.append("Journal local: data/eva_self_improvements.jsonl")
    return "\n".join(lines)

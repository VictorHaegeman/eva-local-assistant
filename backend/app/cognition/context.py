from __future__ import annotations

from dataclasses import dataclass, replace

from app.agents.understanding import UnderstandingFrame
from app.memory.memory_router import RoutedMemoryContext, route_memory
from app.skills.registry import SkillDescriptor, select_skills


@dataclass(frozen=True)
class CognitiveMemoryItem:
    memory_id: int
    content: str
    category: str
    source: str
    cluster_key: str
    score: float


@dataclass(frozen=True)
class CognitiveSkillItem:
    key: str
    label: str
    category: str
    policy_level: str
    tool_hints: tuple[str, ...]
    instructions: str


@dataclass(frozen=True)
class CognitiveContext:
    query: str
    clusters: tuple[str, ...]
    memories: tuple[CognitiveMemoryItem, ...]
    operating_rules: tuple[str, ...]
    skills: tuple[CognitiveSkillItem, ...]
    vector_available: bool
    vector_error: str = ""


def _recent_context_text(conversation_context: list[dict[str, str]], limit: int = 6) -> str:
    parts: list[str] = []
    for message in conversation_context[-limit:]:
        role = message.get("role")
        content = " ".join(str(message.get("content", "")).split())
        if role in {"user", "assistant"} and content:
            label = "Victor" if role == "user" else "Eva"
            parts.append(f"{label}: {content[:420]}")
    return "\n".join(parts)


def _build_query(message: str, conversation_context: list[dict[str, str]], frame: UnderstandingFrame) -> str:
    recent = _recent_context_text(conversation_context)
    parts = [
        message,
        f"Objectif interprete: {frame.interpreted_goal}",
        f"Domaine: {frame.primary_domain}",
        f"Route: {frame.action_plan.route}",
    ]
    if recent:
        parts.append(f"Contexte recent:\n{recent}")
    return "\n".join(parts)


def build_cognitive_context(
    message: str,
    conversation_context: list[dict[str, str]],
    frame: UnderstandingFrame,
    limit: int = 8,
) -> CognitiveContext:
    query = _build_query(message, conversation_context, frame)
    routed: RoutedMemoryContext = route_memory(query, limit=limit)
    selected_skills: tuple[SkillDescriptor, ...] = tuple(select_skills(query, limit=5))

    clusters = tuple(route.cluster.label for route in routed.clusters[:5])
    memories: list[CognitiveMemoryItem] = []
    operating_rules: list[str] = []
    skills: list[CognitiveSkillItem] = []

    for result in routed.results[:limit]:
        memory = result.memory
        item = CognitiveMemoryItem(
            memory_id=memory.id,
            content=memory.content,
            category=memory.category,
            source=memory.source,
            cluster_key=result.cluster_key,
            score=result.score,
        )
        memories.append(item)
        if memory.category == "operating_rule":
            operating_rules.append(memory.content)

    for skill in selected_skills:
        skills.append(
            CognitiveSkillItem(
                key=skill.key,
                label=skill.label,
                category=skill.category,
                policy_level=str(skill.policy_level),
                tool_hints=tuple(skill.tool_hints),
                instructions=skill.instructions,
            )
        )

    return CognitiveContext(
        query=query,
        clusters=clusters,
        memories=tuple(memories),
        operating_rules=tuple(dict.fromkeys(operating_rules[:5])),
        skills=tuple(skills),
        vector_available=routed.vector_available,
        vector_error=routed.vector_error,
    )


def format_cognitive_context(context: CognitiveContext) -> str:
    lines = [
        "Working memory cognitive Eva.",
        f"Clusters actifs: {', '.join(context.clusters) if context.clusters else 'aucun cluster dominant'}.",
        (
            "Memoire vectorielle: active."
            if context.vector_available
            else f"Memoire vectorielle: indisponible ({context.vector_error or 'raison inconnue'})."
        ),
    ]

    if context.operating_rules:
        lines.append("Regles operateur pertinentes:")
        for rule in context.operating_rules:
            lines.append(f"- {rule}")

    if context.memories:
        lines.append("Souvenirs pertinents:")
        for item in context.memories[:8]:
            lines.append(
                f"- [#{item.memory_id} {item.category}/{item.source} score {item.score:.2f}] "
                f"{item.content}"
            )
    else:
        lines.append("Souvenirs pertinents: aucun souvenir specifique trouve.")

    if context.skills:
        lines.append("Skills candidates pour cette demande:")
        for skill in context.skills[:5]:
            tools = ", ".join(skill.tool_hints) if skill.tool_hints else "aucun outil specifique"
            lines.append(
                f"- [{skill.key} | {skill.policy_level} | {skill.category}] "
                f"{skill.label}: {skill.instructions} Tools: {tools}."
            )
    else:
        lines.append("Skills candidates: aucun skill specifique.")

    lines.append(
        "Utilise cette working memory pour choisir l'intention, le plan et les outils. "
        "Ne l'invente pas et ne la recite pas integralement."
    )
    return "\n".join(lines)


def attach_cognitive_context(frame: UnderstandingFrame, context: CognitiveContext) -> UnderstandingFrame:
    summary_parts = []
    if context.clusters:
        summary_parts.append(f"clusters={', '.join(context.clusters[:4])}")
    if context.operating_rules:
        summary_parts.append(f"regles={len(context.operating_rules)}")
    if context.memories:
        summary_parts.append(f"souvenirs={len(context.memories)}")
    if not summary_parts:
        summary_parts.append("aucun souvenir specifique")

    skill_summary = ""
    if context.skills:
        skill_summary = ", ".join(skill.label for skill in context.skills[:4])

    return replace(
        frame,
        cognitive_memory_summary="; ".join(summary_parts),
        cognitive_memory_clusters=context.clusters,
        cognitive_memory_count=len(context.memories),
        cognitive_skill_summary=skill_summary,
        cognitive_skill_keys=tuple(skill.key for skill in context.skills[:5]),
    )

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from app.agents.understanding import UnderstandingFrame
from app.config import settings
from app.cognition.problem_store import ProblemEvent, list_problem_events
from app.cognition.reinforcement_store import (
    ActionRewardStats,
    ReinforcementStoreError,
    list_reward_stats,
    recommend_route_for_state,
)
from app.memory.memory_store import MemoryStoreError, list_memories


PRIVATE_OR_LOCAL_DOMAINS = {
    "gmail",
    "calendar",
    "google_setup",
    "screen",
    "desktop",
    "beeper",
    "linkedin",
    "spotify",
    "cursor",
    "project",
}

EXPLICIT_WEB_MARKERS = (
    "cherche sur internet",
    "recherche internet",
    "va sur internet",
    "trouve sur internet",
    "cherche web",
    "recherche web",
    "news",
    "actu",
    "actualites",
)

DOMAIN_ROUTE_BOOSTS: dict[str, tuple[str, ...]] = {
    "gmail": ("gmail_read", "gmail_reply_audit", "gmail_reply_draft"),
    "calendar": ("calendar_read",),
    "screen": ("screen_read", "desktop_control"),
    "desktop": ("desktop_control", "screen_read"),
    "browser": ("browser_or_video", "web_search"),
    "spotify": ("spotify", "browser_or_video"),
    "beeper": ("beeper_messages", "screen_read"),
    "linkedin": ("linkedin_activity", "linkedin_browser_post", "browser_or_video"),
    "cursor": ("cursor_work", "cursor_agent_setup"),
    "project": ("project_factory", "cursor_work"),
    "web": ("web_search", "browser_or_video"),
}


@dataclass(frozen=True)
class SimilarCase:
    event_id: int
    similarity: float
    domain: str
    expected_outcome: str
    problem_type: str
    tool: str
    status: str
    summary: str
    alternate_routes: tuple[str, ...]


@dataclass(frozen=True)
class MLRouteScore:
    route: str
    score: float
    reasons: tuple[str, ...]


def _normalize(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", str(text or "").lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", _normalize(text))
        if len(token) > 2
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _explicit_web_request(message: str) -> bool:
    normalized = _normalize(message)
    return any(marker in normalized for marker in EXPLICIT_WEB_MARKERS)


def _state_key(frame: UnderstandingFrame) -> str:
    return f"{frame.primary_domain}:{frame.expected_outcome}"


def _stats_for_state(state_key: str) -> dict[str, ActionRewardStats]:
    try:
        stats = list_reward_stats(state_key, limit=24)
    except ReinforcementStoreError:
        return {}
    return {item.action_key: item for item in stats}


def _similar_problem_cases(
    message: str,
    frame: UnderstandingFrame,
    limit: int = 4,
) -> tuple[SimilarCase, ...]:
    query_tokens = _tokens(
        "\n".join(
            (
                message,
                frame.interpreted_goal,
                frame.primary_domain,
                frame.expected_outcome,
            )
        )
    )
    if not query_tokens:
        return ()

    try:
        events = list_problem_events(limit=80)
    except Exception:
        return ()

    cases: list[SimilarCase] = []
    for event in events:
        event_text = "\n".join(
            (
                event.message,
                event.summary,
                event.domain,
                event.expected_outcome,
                event.problem_type,
            )
        )
        similarity = _jaccard(query_tokens, _tokens(event_text))
        if event.domain == frame.primary_domain:
            similarity += 0.14
        if event.expected_outcome == frame.expected_outcome:
            similarity += 0.08
        if str(frame.action_plan.route) in event.alternate_routes:
            similarity += 0.04
        if similarity < 0.16:
            continue
        cases.append(
            SimilarCase(
                event_id=event.id,
                similarity=min(similarity, 1.0),
                domain=event.domain,
                expected_outcome=event.expected_outcome,
                problem_type=event.problem_type,
                tool=event.tool,
                status=event.status,
                summary=event.summary,
                alternate_routes=event.alternate_routes,
            )
        )

    return tuple(sorted(cases, key=lambda item: item.similarity, reverse=True)[:limit])


def _route_score(
    route: str,
    frame: UnderstandingFrame,
    stats_by_route: dict[str, ActionRewardStats],
    similar_cases: tuple[SimilarCase, ...],
    explicit_web: bool,
) -> MLRouteScore:
    score = 0.0
    reasons: list[str] = []
    selected_route = str(frame.action_plan.route)

    if route == selected_route:
        score += 0.28
        reasons.append("route initiale")

    if route in DOMAIN_ROUTE_BOOSTS.get(frame.primary_domain, ()):
        score += 0.38
        reasons.append("route coherente domaine")

    if route in frame.reasoning_routes:
        score += 0.12
        reasons.append("route proposee par le second regard")

    stats = stats_by_route.get(route)
    if stats:
        score += stats.policy_score * 0.42
        score += stats.avg_reward * 0.35
        score += min(stats.attempts, 8) * 0.015
        if stats.penalty_count:
            penalty_ratio = stats.penalty_count / max(stats.attempts, 1)
            score -= min(penalty_ratio * 0.55, 0.55)
        reasons.append(
            f"historique avg={stats.avg_reward:.2f} essais={stats.attempts}"
        )

    for case in similar_cases:
        if route in case.alternate_routes:
            score += 0.18 * case.similarity
            reasons.append(f"cas similaire #{case.event_id}")

    if route == "web_search" and frame.primary_domain in PRIVATE_OR_LOCAL_DOMAINS and not explicit_web:
        score -= 1.35
        reasons.append("web penalise pour donnee locale/privee")

    if route == "generic_chat" and frame.expected_outcome not in {"answer", "clarify"}:
        score -= 0.42
        reasons.append("reponse directe trop faible pour action attendue")

    return MLRouteScore(route=route, score=round(score, 4), reasons=tuple(reasons))


def rank_routes_with_ml_policy(
    routes: list[str],
    frame: UnderstandingFrame,
    message: str,
) -> list[str]:
    if not settings.eva_ml_adaptation_enabled or not routes:
        return routes

    state_key = _state_key(frame)
    stats_by_route = _stats_for_state(state_key)
    similar_cases = _similar_problem_cases(message, frame, limit=settings.eva_ml_adaptation_similar_cases)
    explicit_web = _explicit_web_request(message)
    scored = [
        _route_score(route, frame, stats_by_route, similar_cases, explicit_web)
        for route in routes
    ]

    ranked = sorted(
        enumerate(scored),
        key=lambda item: (item[1].score, -item[0]),
        reverse=True,
    )
    return [score.route for _, score in ranked]


def build_ml_adaptation_context(message: str, frame: UnderstandingFrame) -> str:
    if not settings.eva_ml_adaptation_enabled:
        return "Adaptation ML locale: desactivee."

    state_key = _state_key(frame)
    try:
        recommendation = recommend_route_for_state(state_key, str(frame.action_plan.route))
    except ReinforcementStoreError:
        recommendation = None

    similar_cases = _similar_problem_cases(message, frame, limit=settings.eva_ml_adaptation_similar_cases)
    explicit_web = _explicit_web_request(message)
    candidate_routes = [
        str(frame.action_plan.route),
        *[route for route in frame.reasoning_routes if route != "generic_chat"],
        *DOMAIN_ROUTE_BOOSTS.get(frame.primary_domain, ()),
        "web_search",
        "generic_chat",
    ]
    unique_routes = list(dict.fromkeys(candidate_routes))
    stats_by_route = _stats_for_state(state_key)
    route_scores = [
        _route_score(route, frame, stats_by_route, similar_cases, explicit_web)
        for route in unique_routes[:8]
    ]
    route_scores = sorted(route_scores, key=lambda item: item.score, reverse=True)[:5]

    lines = [
        "Adaptation ML locale active.",
        "Sources appliquees: KNN/cas proches, metrics/rewards, cross-validation, training loop.",
        f"Etat ML: {state_key}.",
        (
            "Regle precision: demande locale/privee, ne pas utiliser web_search sauf demande web explicite."
            if frame.primary_domain in PRIVATE_OR_LOCAL_DOMAINS and not explicit_web
            else "Regle exploration: route web autorisee si elle aide a obtenir une preuve publique."
        ),
    ]

    if recommendation:
        lines.append(f"Reward policy: {recommendation.summary}")
        if recommendation.candidates:
            top = ", ".join(
                f"{item.action_key} avg={item.avg_reward:.2f}/n={item.attempts}"
                for item in recommendation.candidates[:4]
            )
            lines.append(f"Stats routes: {top}.")

    if route_scores:
        lines.append("Scores routes ML:")
        for item in route_scores:
            reason = "; ".join(item.reasons[:3]) or "pas de signal"
            lines.append(f"- {item.route}: {item.score:.2f} ({reason})")

    if similar_cases:
        lines.append("Cas proches du resolver:")
        for case in similar_cases:
            routes = ", ".join(case.alternate_routes[:3]) or "aucune route alternative"
            lines.append(
                f"- #{case.event_id} sim={case.similarity:.2f} {case.domain}/{case.problem_type}: "
                f"{case.summary[:160]} | routes: {routes}"
            )
    else:
        lines.append("Cas proches du resolver: aucun cas assez similaire.")

    lines.append(
        "Decision: choisir la route avec preuve locale attendue, verifier le resultat, puis penaliser les routes hors sujet."
    )
    return "\n".join(lines)


def ml_adaptation_status(limit: int = 30) -> dict[str, Any]:
    try:
        memories = list_memories(limit=500)
    except MemoryStoreError:
        memories = []
    knowledge_memories = [
        memory
        for memory in memories
        if memory.source == "knowledge_pdf" or memory.category == "machine_learning"
    ]
    try:
        stats = list_reward_stats(limit=limit)
    except ReinforcementStoreError:
        stats = []
    try:
        cases = list_problem_events(limit=limit)
    except Exception:
        cases = []

    penalized = [
        item
        for item in stats
        if item.penalty_count > 0 or item.avg_reward < -0.05
    ]
    rewarded = [
        item
        for item in stats
        if item.success_count > 0 and item.avg_reward > 0.05
    ]

    lessons = [
        {
            "course": "KNN",
            "adaptation": "Comparer la demande courante aux cas proches du resolver avant de choisir une route.",
            "status": "active",
        },
        {
            "course": "Metrics evaluation",
            "adaptation": "Mesurer chaque route par reward moyen, penalites, preuves et volume d'essais.",
            "status": "active",
        },
        {
            "course": "Cross-validation",
            "adaptation": "Essayer plusieurs routes candidates et garder celle qui produit une preuve verifiable.",
            "status": "active",
        },
        {
            "course": "Training process",
            "adaptation": "Transformer les erreurs et corrections de Victor en signaux locaux, puis en memoire.",
            "status": "active",
        },
        {
            "course": "Clustering",
            "adaptation": "Utiliser les clusters memoire comme boussole, pas comme prison de recherche.",
            "status": "active",
        },
    ]

    route_quality = []
    for item in sorted(stats, key=lambda stat: stat.policy_score, reverse=True)[:8]:
        route_quality.append(
            {
                "state_key": item.state_key,
                "action_key": item.action_key,
                "attempts": item.attempts,
                "avg_reward": round(item.avg_reward, 4),
                "policy_score": round(item.policy_score, 4),
                "penalty_count": item.penalty_count,
                "success_count": item.success_count,
            }
        )

    return {
        "enabled": settings.eva_ml_adaptation_enabled,
        "knowledge_memories": len(knowledge_memories),
        "rewarded_routes": len(rewarded),
        "penalized_routes": len(penalized),
        "problem_cases": len(cases),
        "similar_case_limit": settings.eva_ml_adaptation_similar_cases,
        "lessons": lessons,
        "route_quality": route_quality,
        "policy": (
            "Eva applique les cours ML comme une couche de decision locale: "
            "similarite de cas, scores, penalites, routes candidates et verification."
        ),
    }


def policy_confidence(value: float) -> int:
    return max(0, min(100, int(math.floor(value * 100))))

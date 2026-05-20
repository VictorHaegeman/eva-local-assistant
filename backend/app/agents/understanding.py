import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from app.agents.action_planner import ActionPlan, build_action_plan
from app.agents.intent_router import UserIntent, classify_user_intent


PrimaryDomain = Literal[
    "gmail",
    "calendar",
    "google_setup",
    "screen",
    "terminal",
    "project",
    "cursor",
    "browser",
    "spotify",
    "desktop",
    "beeper",
    "linkedin",
    "design",
    "web",
    "memory",
    "status",
    "chat",
]

ExpectedOutcome = Literal[
    "answer",
    "read",
    "read_then_summarize",
    "read_then_audit",
    "read_then_open",
    "draft",
    "open",
    "execute_local",
    "diagnose",
    "create_workspace",
    "prepare_prompt",
    "search",
    "clarify",
]

SafetyLevel = Literal["read_only", "local_action", "external_draft", "critical"]


@dataclass(frozen=True)
class UnderstandingFrame:
    raw_message: str
    normalized_message: str
    interpreted_goal: str
    primary_domain: PrimaryDomain
    expected_outcome: ExpectedOutcome
    intent: UserIntent
    action_plan: ActionPlan
    safety_level: SafetyLevel
    requires_context: bool
    context_focus: str
    required_evidence: tuple[str, ...]
    tool_preference: str
    clarification_question: str = ""


def normalize_understanding_text(text: str) -> str:
    without_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )
    return " ".join(without_accents.split())


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _recent_context_summary(messages: list[dict[str, str]], limit: int = 6) -> str:
    recent = [
        message
        for message in messages[-limit:]
        if message.get("role") in {"user", "assistant"} and message.get("content", "").strip()
    ]
    if not recent:
        return ""

    parts: list[str] = []
    for message in recent:
        role = "Victor" if message["role"] == "user" else "Eva"
        content = " ".join(message["content"].split())[:240]
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _is_followup(normalized: str, conversation_context: list[dict[str, str]]) -> bool:
    if not conversation_context:
        return False

    words = re.findall(r"[a-z0-9_]+", normalized)
    if len(words) <= 6:
        return True

    return _has_any(
        normalized,
        (
            "comme avant",
            "comme la derniere fois",
            "fais pareil",
            "continue",
            "reprends",
            "celui la",
            "celle la",
            "ce mail",
            "ce message",
            "lui repondre",
            "reponds lui",
            "ouvre le",
            "ouvre la",
            "le dernier",
            "la derniere",
        ),
    )


def _domain_from_message(
    normalized: str,
    intent: UserIntent,
    conversation_context: list[dict[str, str]] | None = None,
) -> PrimaryDomain:
    if intent.name in {"gmail_read", "gmail_reply_audit", "gmail_reply_draft"}:
        return "gmail"
    if intent.name == "calendar_read":
        return "calendar"
    if intent.name == "google_oauth_setup":
        return "google_setup"
    if intent.name == "screen_read":
        return "screen"
    if intent.name == "terminal_error":
        return "terminal"
    if intent.name == "project_factory":
        return "project"
    if intent.name == "cursor_work":
        return "cursor"
    if intent.name == "local_status":
        return "status"

    context_text = normalize_understanding_text(_recent_context_summary(conversation_context or []))
    if _is_followup(normalized, conversation_context or []):
        if _has_any(context_text, ("gmail", "mail", "email", "inbox", "expediteur", "objet")):
            return "gmail"
        if _has_any(context_text, ("beeper", "message", "conversation", "dm")):
            return "beeper"
        if _has_any(context_text, ("cursor", "codex", "repo", "projet")):
            return "cursor"

    if _has_any(normalized, ("spotify", "musique", "playlist", "chanson")):
        return "spotify"
    if _has_any(normalized, ("beeper", "whatsapp", "telegram", "message beeper", "mes messages")):
        return "beeper"
    if _has_any(normalized, ("linkedin", "post linkedin", "commentaire linkedin")):
        return "linkedin"
    if _has_any(normalized, ("stitch", "maquette", "design", "interface", "ui ")):
        return "design"
    if _has_any(normalized, ("clique", "click", "bouton", "appuie", "ecran", "pixels")):
        return "screen"
    if _has_any(normalized, ("youtube", "video", "brave", "navigateur", "site", "onglet")):
        return "browser"
    if _has_any(normalized, ("cherche sur internet", "recherche internet", "va sur internet", "trouve sur internet")):
        return "web"
    if _has_any(normalized, ("memoire", "souviens", "retiens", "apprends")):
        return "memory"
    return "chat"


def _expected_outcome(normalized: str, intent: UserIntent, domain: PrimaryDomain) -> ExpectedOutcome:
    if intent.name == "gmail_reply_audit":
        return "read_then_audit"
    if intent.name == "gmail_reply_draft":
        return "draft"
    if intent.name == "gmail_read":
        if _has_any(normalized, ("ouvre", "ouvrir", "lien")):
            return "read_then_open"
        return "read_then_summarize"
    if intent.name == "calendar_read":
        return "read_then_summarize"
    if intent.name == "terminal_error":
        return "diagnose"
    if intent.name == "project_factory":
        return "create_workspace"
    if intent.name == "cursor_work":
        return "prepare_prompt"

    reply_markers = (
        "reponds",
        "repond ",
        "reponse",
        "redige",
        "ecris",
        "brouillon",
        "pret a envoyer",
    )
    if domain == "gmail" and _has_any(normalized, reply_markers):
        return "draft"
    if domain == "gmail" and _has_any(normalized, ("ouvre", "ouvrir", "affiche")):
        return "read_then_open"
    if domain == "beeper" and _has_any(normalized, reply_markers):
        return "draft"

    if domain in {"spotify", "browser", "screen", "desktop"}:
        return "open" if domain in {"spotify", "browser"} else "execute_local"
    if domain in {"beeper", "linkedin"} and _has_any(normalized, ("repond", "redige", "ecris", "brouillon")):
        return "draft"
    if domain == "web":
        return "search"
    if _has_any(normalized, ("resume", "resumes", "debrief", "analyse", "lis")):
        return "read_then_summarize"
    return "answer"


def _safety_level(domain: PrimaryDomain, outcome: ExpectedOutcome, normalized: str) -> SafetyLevel:
    if _has_any(
        normalized,
        (
            "envoie",
            "envoyer",
            "publie",
            "poster",
            "push",
            "supprime",
            "delete",
            "paiement",
            "achat",
        ),
    ):
        return "critical"
    if outcome == "draft" or domain in {"gmail", "beeper", "linkedin", "cursor", "design"}:
        return "external_draft"
    if outcome in {"open", "execute_local", "create_workspace", "prepare_prompt"}:
        return "local_action"
    return "read_only"


def _required_evidence(domain: PrimaryDomain, outcome: ExpectedOutcome) -> tuple[str, ...]:
    if domain == "gmail":
        if outcome == "read_then_audit":
            return ("mail reel lu via Gmail API", "thread verifie pour savoir si Victor a deja repondu")
        if outcome == "draft":
            return ("mail source reel lu via Gmail API", "brouillon prepare sans envoi")
        return ("mails reels lus via Gmail API",)
    if domain == "calendar":
        return ("evenements reels lus via Google Calendar",)
    if domain == "screen":
        return ("capture ecran locale", "interpretation vision avant clic")
    if domain == "terminal":
        return ("erreur terminal analysee", "correctif connu si disponible")
    if domain == "project":
        return ("brief projet interprete", "workspace et actions verifiables")
    if domain == "browser":
        return ("URL ou intention web interpretee", "Brave ouvert si action fiable")
    if domain == "spotify":
        return ("requete musique interpretee", "Spotify ou recherche web ouverte")
    if domain == "web":
        return ("resultats web cites dans le contexte",)
    return ("objectif interprete",)


def _tool_preference(domain: PrimaryDomain) -> str:
    return {
        "gmail": "gmail_client",
        "calendar": "google_calendar",
        "google_setup": "gmail_auth",
        "screen": "screen_reader_or_visual_action",
        "terminal": "terminal_doctor",
        "project": "project_factory",
        "cursor": "cursor_bridge",
        "browser": "browser_assistant",
        "spotify": "spotify_assistant",
        "desktop": "desktop_automation",
        "beeper": "beeper_assistant",
        "linkedin": "linkedin_assistant",
        "design": "google_stitch_bridge",
        "web": "web_search",
        "memory": "memory_router",
        "status": "doctor",
        "chat": "ollama_chat",
    }[domain]


def _interpreted_goal(
    message: str,
    intent: UserIntent,
    domain: PrimaryDomain,
    outcome: ExpectedOutcome,
) -> str:
    clean_message = " ".join(message.split())
    if domain == "gmail" and outcome == "read_then_audit":
        return "Lire les mails reels lies au sujet demande, puis distinguer ceux deja repondus de ceux a traiter."
    if domain == "gmail" and outcome == "draft":
        return "Lire le mail source reel, comprendre le besoin, puis preparer un brouillon sans envoyer."
    if domain == "gmail":
        return "Lire les mails reels pertinents avant d'ouvrir des liens ou de resumer."
    if domain == "screen":
        return "Observer l'ecran local et identifier l'action UI utile avant tout clic."
    if domain == "browser":
        return "Ouvrir le bon site dans Brave uniquement apres avoir compris le besoin web."
    if domain == "spotify":
        return "Ouvrir Spotify ou la bonne recherche musicale selon la demande."
    if domain == "project":
        return "Transformer l'idee en plan projet executable avec workspace, prompt Cursor et Git."
    if domain == "cursor":
        return "Preparer une session de travail Cursor/Codex avec contexte projet."
    if domain == "web":
        return "Chercher sur internet, filtrer les resultats utiles, puis repondre avec le contexte trouve."
    if intent.name != "generic_chat":
        return intent.summary
    return f"Comprendre puis repondre a la demande: {clean_message[:280]}"


def _clarification_question(
    normalized: str,
    domain: PrimaryDomain,
    outcome: ExpectedOutcome,
    conversation_context: list[dict[str, str]],
) -> str:
    if _is_followup(normalized, conversation_context):
        return ""
    if domain == "gmail" and outcome in {"draft", "read_then_open"}:
        has_target = _has_any(
            normalized,
            (
                "dernier",
                "dreamlense",
                "appartement",
                "bienici",
                "pap",
                "alerte",
                "prospect",
                "client",
                "sujet",
            ),
        )
        if not has_target:
            return "Quel mail dois-je utiliser exactement: le dernier recu, un expediteur, ou un sujet ?"
    return ""


def build_understanding_frame(
    message: str,
    conversation_context: list[dict[str, str]] | None = None,
    trusted_actions: bool = False,
) -> UnderstandingFrame:
    context = conversation_context or []
    normalized = normalize_understanding_text(message)
    intent = classify_user_intent(message)
    action_plan = build_action_plan(message, intent, trusted_actions=trusted_actions)
    domain = _domain_from_message(normalized, intent, context)
    outcome = _expected_outcome(normalized, intent, domain)
    context_summary = _recent_context_summary(context)
    requires_context = _is_followup(normalized, context) or domain in {
        "gmail",
        "beeper",
        "cursor",
        "project",
        "memory",
    }

    return UnderstandingFrame(
        raw_message=message,
        normalized_message=normalized,
        interpreted_goal=_interpreted_goal(message, intent, domain, outcome),
        primary_domain=domain,
        expected_outcome=outcome,
        intent=intent,
        action_plan=action_plan,
        safety_level=_safety_level(domain, outcome, normalized),
        requires_context=requires_context,
        context_focus=context_summary,
        required_evidence=_required_evidence(domain, outcome),
        tool_preference=_tool_preference(domain),
        clarification_question=_clarification_question(normalized, domain, outcome, context),
    )


def format_understanding_context(frame: UnderstandingFrame) -> str:
    lines = [
        "Cadre de comprehension Eva avant toute reponse.",
        f"Objectif interprete: {frame.interpreted_goal}",
        f"Domaine principal: {frame.primary_domain}",
        f"Resultat attendu: {frame.expected_outcome}",
        f"Intent: {frame.intent.name} ({round(frame.intent.confidence * 100)}%)",
        f"Outil prefere: {frame.tool_preference}",
        f"Niveau de securite: {frame.safety_level}",
        "Preuves a obtenir avant de conclure:",
    ]
    for evidence in frame.required_evidence:
        lines.append(f"- {evidence}")
    if frame.requires_context:
        lines.append("Contexte conversationnel utile:")
        lines.append(frame.context_focus or "Aucun contexte precedent disponible.")
    if frame.clarification_question:
        lines.append(f"Question de clarification: {frame.clarification_question}")
    lines.append(
        "Ne recite pas ce cadre. Utilise-le pour choisir l'outil, lire les bonnes sources, "
        "eviter l'invention et dire clairement ce qui est reellement fait."
    )
    return "\n".join(lines)


def understanding_to_dict(frame: UnderstandingFrame) -> dict[str, object]:
    return {
        "raw_message": frame.raw_message,
        "interpreted_goal": frame.interpreted_goal,
        "primary_domain": frame.primary_domain,
        "expected_outcome": frame.expected_outcome,
        "intent": {
            "name": frame.intent.name,
            "confidence": frame.intent.confidence,
            "summary": frame.intent.summary,
            "caution": frame.intent.caution,
        },
        "action_plan": {
            "route": frame.action_plan.route,
            "goal": frame.action_plan.goal,
            "confidence": frame.action_plan.confidence,
            "policy_level": frame.action_plan.policy_level,
            "trusted_actions": frame.action_plan.trusted_actions,
            "caution": frame.action_plan.caution,
            "steps": [
                {
                    "label": step.label,
                    "status": step.status,
                    "tool": step.tool,
                    "auto": step.auto,
                }
                for step in frame.action_plan.steps
            ],
        },
        "safety_level": frame.safety_level,
        "requires_context": frame.requires_context,
        "context_focus": frame.context_focus,
        "required_evidence": list(frame.required_evidence),
        "tool_preference": frame.tool_preference,
        "clarification_question": frame.clarification_question,
    }

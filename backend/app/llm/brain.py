"""Couche cerveau configurable d'Eva.

Cette couche choisit le moteur LLM (Groq gratuit ou Ollama local) sans changer le
reste du code: les modules continuent d'appeler `ask_ollama` / `ask_ollama_json`,
qui délèguent maintenant à `brain_chat`.

Principe:
- `EVA_BRAIN_PROVIDER=auto` (défaut): Groq si une clé est configurée, sinon Ollama.
- `EVA_BRAIN_PROVIDER=groq`: force Groq si la clé existe, sinon retombe sur Ollama.
- `EVA_BRAIN_PROVIDER=ollama`: force le local hors-ligne.
- En mode auto, si Groq échoue (réseau/clé), Eva retombe automatiquement sur Ollama.
"""

from typing import Any, Literal

import httpx

from app.config import settings


class BrainError(Exception):
    """Raised when Eva's brain provider cannot return a usable answer."""


Tier = Literal["chat", "reasoning"]


def resolve_provider() -> str:
    """Retourne le moteur effectif: 'groq' ou 'ollama'."""
    provider = (settings.eva_brain_provider or "auto").strip().lower()
    has_groq = bool(settings.groq_api_key.strip())
    if provider == "groq":
        return "groq" if has_groq else "ollama"
    if provider == "ollama":
        return "ollama"
    # auto
    return "groq" if has_groq else "ollama"


def model_for_tier(tier: Tier, provider: str) -> str:
    """Mappe un niveau de réflexion vers le modèle concret du moteur choisi."""
    if provider == "groq":
        if tier == "reasoning":
            return settings.groq_reasoning_model or settings.groq_model
        return settings.groq_model
    if tier == "reasoning":
        return settings.ollama_reasoning_model
    return settings.ollama_model


def _looks_like_missing_model(error_text: str) -> bool:
    normalized = error_text.lower()
    return "model" in normalized and (
        "not found" in normalized
        or "pull" in normalized
        or "does not exist" in normalized
        or "introuvable" in normalized
        or "decommissioned" in normalized
    )


def _extract_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()
    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("detail")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message.strip()
        if isinstance(error, str):
            return error.strip()
    return response.text.strip()


async def _ollama_chat(
    messages: list[dict[str, Any]],
    model: str,
    temperature: float,
    timeout_seconds: float,
    json_mode: bool,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {"temperature": temperature},
    }
    if json_mode:
        payload["format"] = "json"

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=timeout_seconds,
        ) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise BrainError(
            "Ollama n'est pas lance ou n'est pas accessible sur "
            f"{settings.ollama_base_url}. Lance Ollama, puis reessaie."
        ) from exc
    except httpx.TimeoutException as exc:
        raise BrainError(
            "L'API Ollama ne repond pas dans le delai attendu. "
            "Verifie qu'Ollama tourne correctement ou utilise un modele plus leger."
        ) from exc
    except httpx.HTTPStatusError as exc:
        error_text = _extract_error_text(exc.response)
        if exc.response.status_code == 404 or _looks_like_missing_model(error_text):
            raise BrainError(
                f"Le modele Ollama '{model}' n'est pas installe. "
                f"Lance: ollama pull {model}"
            ) from exc
        detail = f" Detail Ollama: {error_text}" if error_text else ""
        raise BrainError(
            f"L'API Ollama a repondu avec une erreur HTTP {exc.response.status_code}.{detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise BrainError(
            "Impossible de contacter correctement l'API Ollama. "
            "Verifie qu'Ollama est lance et accessible."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise BrainError("L'API Ollama a repondu, mais sa reponse n'est pas du JSON valide.") from exc

    if isinstance(data, dict) and data.get("error"):
        error_text = str(data["error"])
        if _looks_like_missing_model(error_text):
            raise BrainError(
                f"Le modele Ollama '{model}' n'est pas installe. Lance: ollama pull {model}"
            )
        raise BrainError(f"Erreur Ollama: {error_text}")

    if not isinstance(data, dict):
        raise BrainError("Ollama a renvoye une reponse inattendue.")

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise BrainError("Ollama n'a pas renvoye de reponse exploitable.")
    return content


async def _groq_chat(
    messages: list[dict[str, Any]],
    model: str,
    temperature: float,
    timeout_seconds: float,
    json_mode: bool,
) -> str:
    api_key = settings.groq_api_key.strip()
    if not api_key:
        raise BrainError("Clé Groq absente: configure GROQ_API_KEY pour utiliser le cerveau Groq.")

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    base_url = settings.groq_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise BrainError("Le cerveau Groq n'est pas joignable (réseau). Repli local possible.") from exc
    except httpx.TimeoutException as exc:
        raise BrainError("Le cerveau Groq ne répond pas assez vite.") from exc
    except httpx.HTTPStatusError as exc:
        error_text = _extract_error_text(exc.response)
        if exc.response.status_code in {401, 403}:
            raise BrainError("Clé Groq invalide ou refusée (401/403). Vérifie GROQ_API_KEY.") from exc
        if exc.response.status_code == 429:
            raise BrainError("Quota Groq atteint pour le moment (429). Réessaie plus tard ou repli local.") from exc
        detail = f" Detail Groq: {error_text}" if error_text else ""
        raise BrainError(
            f"Le cerveau Groq a répondu avec une erreur HTTP {exc.response.status_code}.{detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise BrainError("Impossible de contacter correctement l'API Groq.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise BrainError("Le cerveau Groq a renvoyé une réponse non JSON.") from exc

    if not isinstance(data, dict):
        raise BrainError("Le cerveau Groq a renvoyé une réponse inattendue.")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise BrainError("Le cerveau Groq n'a pas renvoyé de choix exploitable.")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = (message or {}).get("content", "") if isinstance(message, dict) else ""
    content = content.strip() if isinstance(content, str) else ""
    if not content:
        raise BrainError("Le cerveau Groq n'a pas renvoyé de contenu exploitable.")
    return content


async def brain_chat(
    messages: list[dict[str, Any]],
    *,
    tier: Tier = "chat",
    temperature: float = 0.7,
    timeout_seconds: float | None = None,
    json_mode: bool = False,
) -> str:
    """Envoie une conversation au moteur choisi et renvoie le contenu texte.

    En mode `auto`, un échec Groq (réseau/clé/quota) bascule automatiquement sur
    Ollama pour qu'Eva continue de répondre hors-ligne.
    """
    provider = resolve_provider()
    raw_provider = (settings.eva_brain_provider or "auto").strip().lower()

    if provider == "groq":
        groq_timeout = timeout_seconds or settings.groq_timeout_seconds
        try:
            return await _groq_chat(
                messages,
                model_for_tier(tier, "groq"),
                temperature,
                groq_timeout,
                json_mode,
            )
        except BrainError:
            if raw_provider == "auto":
                ollama_timeout = timeout_seconds or (
                    settings.ollama_reasoning_timeout_seconds
                    if tier == "reasoning"
                    else settings.ollama_timeout_seconds
                )
                return await _ollama_chat(
                    messages,
                    model_for_tier(tier, "ollama"),
                    temperature,
                    ollama_timeout,
                    json_mode,
                )
            raise

    ollama_timeout = timeout_seconds or (
        settings.ollama_reasoning_timeout_seconds
        if tier == "reasoning"
        else settings.ollama_timeout_seconds
    )
    return await _ollama_chat(
        messages,
        model_for_tier(tier, "ollama"),
        temperature,
        ollama_timeout,
        json_mode,
    )

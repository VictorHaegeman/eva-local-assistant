"""Couche cerveau configurable et auto-réparable d'Eva.

Eva choisit le moteur LLM sans changer le reste du code (les modules appellent
toujours `ask_ollama` / `ask_ollama_json`, qui délèguent à `brain_chat`).

Fournisseurs supportés:
- groq        (gratuit, rapide)            cle: GROQ_API_KEY
- openrouter  (gratuit, ~beaucoup de modeles, peu de depreciation)  cle: OPENROUTER_API_KEY
- gemini      (gratuit, Google AI Studio)  cle: GEMINI_API_KEY
- ollama      (100% local, sans cle)

EVA_BRAIN_PROVIDER = auto | groq | openrouter | gemini | ollama
- auto: prend le premier fournisseur cloud dont la cle est definie, sinon Ollama local.
- En mode auto, si le cloud echoue (reseau/cle/quota), Eva retombe sur Ollama.

Auto-reparation: si un modele est deprecie/introuvable (ex: Groq retire un modele),
Eva tente automatiquement le suivant dans une liste de modeles connus, sans intervention.
"""

from typing import Any, Literal

import httpx

from app.config import settings


class BrainError(Exception):
    """Raised when Eva's brain provider cannot return a usable answer."""


class BrainModelError(BrainError):
    """Raised when a specific model is unavailable (deprecated / not found)."""


Tier = Literal["chat", "reasoning"]

# Fournisseurs cloud, par ordre de priorite en mode auto.
CLOUD_PROVIDERS: tuple[str, ...] = ("groq", "openrouter", "gemini")

# Modeles connus-bons par fournisseur (juin 2026), utilises pour l'auto-reparation.
PROVIDER_FALLBACK_MODELS: dict[str, tuple[str, ...]] = {
    # llama-3.3-70b-versatile deprecie le 17/06/2026 -> gpt-oss puis qwen.
    "groq": ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.6-27b"),
    # OpenRouter: une cle, beaucoup de modeles gratuits (suffixe :free).
    "openrouter": (
        "deepseek/deepseek-chat-v3:free",
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-coder:free",
    ),
    # Gemini 2.0 deprecie le 01/06/2026 -> 2.5 / 3 Flash.
    "gemini": ("gemini-2.5-flash", "gemini-3-flash"),
}


def _provider_config(provider: str) -> tuple[str, str]:
    """Retourne (api_key, base_url) pour un fournisseur cloud."""
    if provider == "groq":
        return settings.groq_api_key, settings.groq_base_url
    if provider == "openrouter":
        return (
            getattr(settings, "openrouter_api_key", ""),
            getattr(settings, "openrouter_base_url", "https://openrouter.ai/api/v1"),
        )
    if provider == "gemini":
        return (
            getattr(settings, "gemini_api_key", ""),
            getattr(settings, "gemini_base_url", "https://generativelanguage.googleapis.com/v1beta/openai"),
        )
    return "", ""


def resolve_provider() -> str:
    """Retourne le moteur effectif: 'groq' | 'openrouter' | 'gemini' | 'ollama'."""
    provider = (settings.eva_brain_provider or "auto").strip().lower()
    if provider in CLOUD_PROVIDERS:
        key, _ = _provider_config(provider)
        return provider if key.strip() else "ollama"
    if provider == "ollama":
        return "ollama"
    # auto: premier fournisseur cloud configure, sinon local.
    for candidate in CLOUD_PROVIDERS:
        key, _ = _provider_config(candidate)
        if key.strip():
            return candidate
    return "ollama"


def model_for_tier(tier: Tier, provider: str) -> str:
    """Mappe un niveau de réflexion vers le modèle concret du moteur choisi."""
    if provider == "ollama":
        return settings.ollama_reasoning_model if tier == "reasoning" else settings.ollama_model
    attr = f"{provider}_reasoning_model" if tier == "reasoning" else f"{provider}_model"
    configured = str(getattr(settings, attr, "") or "").strip()
    if configured:
        return configured
    fallbacks = PROVIDER_FALLBACK_MODELS.get(provider, ())
    return fallbacks[0] if fallbacks else ""


def _candidate_models(provider: str, model: str) -> list[str]:
    """Modèle demandé d'abord, puis les autres modèles connus (auto-réparation)."""
    candidates = [model] if model else []
    for fallback in PROVIDER_FALLBACK_MODELS.get(provider, ()):
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates or [model]


def _looks_like_missing_model(error_text: str) -> bool:
    normalized = error_text.lower()
    return "model" in normalized and (
        "not found" in normalized
        or "pull" in normalized
        or "does not exist" in normalized
        or "introuvable" in normalized
        or "decommissioned" in normalized
        or "deprecated" in normalized
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
                f"Le modele Ollama '{model}' n'est pas installe. Lance: ollama pull {model}"
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
            raise BrainError(f"Le modele Ollama '{model}' n'est pas installe. Lance: ollama pull {model}")
        raise BrainError(f"Erreur Ollama: {error_text}")

    if not isinstance(data, dict):
        raise BrainError("Ollama a renvoye une reponse inattendue.")

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise BrainError("Ollama n'a pas renvoye de reponse exploitable.")
    return content


async def _openai_compatible_chat(
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    timeout_seconds: float,
    json_mode: bool,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    # Les modeles gpt-oss (Groq) renvoient leur raisonnement dans un champ separe.
    if provider == "groq" and model.startswith("openai/gpt-oss"):
        payload["include_reasoning"] = False

    url = f"{base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise BrainError(f"Le cerveau {provider} n'est pas joignable (réseau).") from exc
    except httpx.TimeoutException as exc:
        raise BrainError(f"Le cerveau {provider} ne répond pas assez vite.") from exc
    except httpx.HTTPStatusError as exc:
        error_text = _extract_error_text(exc.response)
        status = exc.response.status_code
        if status == 404 or _looks_like_missing_model(error_text):
            raise BrainModelError(f"Modele '{model}' indisponible chez {provider}: {error_text}") from exc
        if status in {401, 403}:
            raise BrainError(f"Clé {provider} invalide ou refusée ({status}). Vérifie la clé.") from exc
        if status == 429:
            raise BrainError(f"Quota {provider} atteint pour le moment (429). Réessaie plus tard.") from exc
        detail = f" Detail {provider}: {error_text}" if error_text else ""
        raise BrainError(f"Le cerveau {provider} a répondu avec une erreur HTTP {status}.{detail}") from exc
    except httpx.HTTPError as exc:
        raise BrainError(f"Impossible de contacter correctement l'API {provider}.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise BrainError(f"Le cerveau {provider} a renvoyé une réponse non JSON.") from exc

    if not isinstance(data, dict):
        raise BrainError(f"Le cerveau {provider} a renvoyé une réponse inattendue.")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        # Certaines erreurs arrivent en 200 avec un champ error.
        err = data.get("error")
        if isinstance(err, dict) and _looks_like_missing_model(str(err.get("message", ""))):
            raise BrainModelError(f"Modele '{model}' indisponible chez {provider}.")
        raise BrainError(f"Le cerveau {provider} n'a pas renvoyé de choix exploitable.")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = (message or {}).get("content", "") if isinstance(message, dict) else ""
    content = content.strip() if isinstance(content, str) else ""
    if not content:
        raise BrainError(f"Le cerveau {provider} n'a pas renvoyé de contenu exploitable.")
    return content


async def _cloud_chat(
    provider: str,
    messages: list[dict[str, Any]],
    model: str,
    temperature: float,
    timeout_seconds: float,
    json_mode: bool,
) -> str:
    api_key, base_url = _provider_config(provider)
    if not api_key.strip():
        raise BrainError(f"Clé {provider} absente.")

    last_error: BrainError | None = None
    for candidate in _candidate_models(provider, model):
        try:
            return await _openai_compatible_chat(
                provider, base_url, api_key.strip(), candidate, messages, temperature, timeout_seconds, json_mode
            )
        except BrainModelError as exc:
            # Modele deprecie/introuvable: on tente le suivant (auto-reparation).
            last_error = exc
            continue
    raise last_error or BrainError(f"Aucun modele {provider} disponible.")


def _cloud_timeout(provider: str, tier: Tier, override: float | None) -> float:
    if override:
        return override
    return float(getattr(settings, f"{provider}_timeout_seconds", settings.groq_timeout_seconds))


def _ollama_timeout(tier: Tier, override: float | None) -> float:
    if override:
        return override
    return (
        settings.ollama_reasoning_timeout_seconds
        if tier == "reasoning"
        else settings.ollama_timeout_seconds
    )


async def brain_chat(
    messages: list[dict[str, Any]],
    *,
    tier: Tier = "chat",
    temperature: float = 0.7,
    timeout_seconds: float | None = None,
    json_mode: bool = False,
) -> str:
    """Envoie une conversation au moteur choisi et renvoie le contenu texte.

    En mode `auto`, un échec cloud (réseau/clé/quota/modèle) bascule sur Ollama
    pour qu'Eva continue de répondre hors-ligne.
    """
    provider = resolve_provider()
    raw_provider = (settings.eva_brain_provider or "auto").strip().lower()

    if provider in CLOUD_PROVIDERS:
        try:
            return await _cloud_chat(
                provider,
                messages,
                model_for_tier(tier, provider),
                temperature,
                _cloud_timeout(provider, tier, timeout_seconds),
                json_mode,
            )
        except BrainError:
            if raw_provider == "auto":
                return await _ollama_chat(
                    messages,
                    model_for_tier(tier, "ollama"),
                    temperature,
                    _ollama_timeout(tier, timeout_seconds),
                    json_mode,
                )
            raise

    return await _ollama_chat(
        messages,
        model_for_tier(tier, "ollama"),
        temperature,
        _ollama_timeout(tier, timeout_seconds),
        json_mode,
    )

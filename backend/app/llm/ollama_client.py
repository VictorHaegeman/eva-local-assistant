import json
import re
from typing import Any, Literal, TypedDict

import httpx

from app.agents.modes import get_mode_prompt
from app.agents.roles import build_roles_prompt_context
from app.config import settings
from app.memory.memory_store import (
    MemoryStoreError,
    build_memory_prompt_context,
)
from app.memory.memory_router import build_relevant_memory_prompt_context
from app.memory.obsidian_store import ObsidianMemoryError, build_obsidian_prompt_context
from app.memory.profile_store import ProfileStoreError, build_profile_prompt_context
from app.prompts.system_prompt import EVA_SYSTEM_PROMPT
from app.skills.registry import build_skills_prompt_context


class OllamaClientError(Exception):
    """Raised when Eva cannot get a usable answer from Ollama."""


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            raise OllamaClientError("Ollama n'a pas renvoye de JSON exploitable.")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise OllamaClientError("Ollama a renvoye un JSON invalide.") from exc

    if not isinstance(data, dict):
        raise OllamaClientError("Ollama a renvoye un JSON inattendu.")
    return data


def _extract_ollama_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()

    if isinstance(payload, dict):
        error = payload.get("error") or payload.get("detail")
        if isinstance(error, str):
            return error.strip()

    return response.text.strip()


def _looks_like_missing_model(error_text: str) -> bool:
    normalized = error_text.lower()
    return (
        "model" in normalized
        and (
            "not found" in normalized
            or "pull" in normalized
            or "does not exist" in normalized
            or "introuvable" in normalized
        )
    )


async def ask_ollama(
    messages: list[ChatMessage],
    extra_context: str | None = None,
    mode: str = "chat",
) -> str:
    try:
        latest_user_message = next(
            (message["content"] for message in reversed(messages) if message["role"] == "user"),
            "",
        )
        system_prompt = (
            f"{EVA_SYSTEM_PROMPT}\n\n"
            f"{get_mode_prompt(mode)}\n\n"
            f"{build_profile_prompt_context()}\n\n"
            f"{build_memory_prompt_context()}\n\n"
            f"{build_relevant_memory_prompt_context(latest_user_message)}\n\n"
            f"{build_obsidian_prompt_context(latest_user_message)}\n\n"
            f"{build_skills_prompt_context(latest_user_message)}\n\n"
            f"{build_roles_prompt_context(latest_user_message, mode)}"
        )
        if extra_context:
            system_prompt = f"{system_prompt}\n\nContexte supplementaire:\n{extra_context}"
    except (ProfileStoreError, MemoryStoreError, ObsidianMemoryError) as exc:
        raise OllamaClientError(str(exc)) from exc

    payload = {
        "model": settings.ollama_model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "options": {
            "temperature": settings.ollama_temperature,
        },
    }

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=settings.ollama_timeout_seconds,
        ) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise OllamaClientError(
            "Ollama n'est pas lance ou n'est pas accessible sur "
            f"{settings.ollama_base_url}. Lance Ollama, puis reessaie."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaClientError(
            "L'API Ollama ne repond pas dans le delai attendu. "
            "Verifie qu'Ollama tourne correctement ou utilise un modele plus leger."
        ) from exc
    except httpx.HTTPStatusError as exc:
        error_text = _extract_ollama_error(exc.response)
        if exc.response.status_code == 404 or _looks_like_missing_model(error_text):
            raise OllamaClientError(
                f"Le modele Ollama '{settings.ollama_model}' n'est pas installe. "
                f"Lance: ollama pull {settings.ollama_model}"
            ) from exc

        detail = f" Detail Ollama: {error_text}" if error_text else ""
        raise OllamaClientError(
            f"L'API Ollama a repondu avec une erreur HTTP "
            f"{exc.response.status_code}.{detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise OllamaClientError(
            "Impossible de contacter correctement l'API Ollama. "
            "Verifie qu'Ollama est lance et accessible."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaClientError(
            "L'API Ollama a repondu, mais sa reponse n'est pas du JSON valide."
        ) from exc

    if isinstance(data, dict) and data.get("error"):
        error_text = str(data["error"])
        if _looks_like_missing_model(error_text):
            raise OllamaClientError(
                f"Le modele Ollama '{settings.ollama_model}' n'est pas installe. "
                f"Lance: ollama pull {settings.ollama_model}"
            )

        raise OllamaClientError(f"Erreur Ollama: {error_text}")

    if not isinstance(data, dict):
        raise OllamaClientError("Ollama a renvoye une reponse inattendue.")

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise OllamaClientError("Ollama n'a pas renvoye de reponse exploitable.")

    return content


async def ask_ollama_json(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
    temperature: float = 0.1,
) -> dict[str, Any]:
    payload = {
        "model": model or settings.ollama_reasoning_model,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "options": {
            "temperature": temperature,
        },
    }

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=timeout_seconds or settings.ollama_reasoning_timeout_seconds,
        ) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise OllamaClientError(
            "Ollama n'est pas lance ou n'est pas accessible pour l'interpretation locale."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaClientError(
            "Le modele de raisonnement Ollama ne repond pas assez vite."
        ) from exc
    except httpx.HTTPStatusError as exc:
        error_text = _extract_ollama_error(exc.response)
        selected_model = model or settings.ollama_reasoning_model
        if exc.response.status_code == 404 or _looks_like_missing_model(error_text):
            raise OllamaClientError(
                f"Le modele de raisonnement Ollama '{selected_model}' n'est pas installe. "
                f"Lance: ollama pull {selected_model}"
            ) from exc
        detail = f" Detail Ollama: {error_text}" if error_text else ""
        raise OllamaClientError(
            f"L'API Ollama a refuse l'interpretation JSON avec HTTP {exc.response.status_code}.{detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise OllamaClientError("Impossible de contacter l'API Ollama pour le JSON.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaClientError("Ollama JSON a renvoye une reponse non JSON.") from exc

    if isinstance(data, dict) and data.get("error"):
        error_text = str(data["error"])
        selected_model = model or settings.ollama_reasoning_model
        if _looks_like_missing_model(error_text):
            raise OllamaClientError(
                f"Le modele de raisonnement Ollama '{selected_model}' n'est pas installe. "
                f"Lance: ollama pull {selected_model}"
            )
        raise OllamaClientError(f"Erreur Ollama JSON: {error_text}")

    if not isinstance(data, dict):
        raise OllamaClientError("Ollama JSON a renvoye une reponse inattendue.")

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise OllamaClientError("Ollama JSON n'a pas renvoye de contenu exploitable.")

    return _extract_json_object(content)


async def ask_ollama_vision(
    image_base64: str,
    prompt: str,
    model: str,
) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64],
            }
        ],
        "options": {
            "temperature": 0.1,
        },
    }

    try:
        async with httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=max(settings.ollama_timeout_seconds, 120.0),
        ) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise OllamaClientError(
            "Ollama n'est pas lance ou n'est pas accessible pour l'analyse ecran."
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaClientError(
            "Le modele vision Ollama ne repond pas assez vite. Utilise un modele plus leger."
        ) from exc
    except httpx.HTTPStatusError as exc:
        error_text = _extract_ollama_error(exc.response)
        if exc.response.status_code == 404 or _looks_like_missing_model(error_text):
            raise OllamaClientError(
                f"Le modele vision Ollama '{model}' n'est pas installe. Lance: ollama pull {model}"
            ) from exc
        detail = f" Detail Ollama: {error_text}" if error_text else ""
        raise OllamaClientError(
            f"L'API Ollama vision a repondu avec une erreur HTTP {exc.response.status_code}.{detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise OllamaClientError("Impossible de contacter l'API Ollama vision.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaClientError("Ollama vision a renvoye une reponse non JSON.") from exc

    if isinstance(data, dict) and data.get("error"):
        error_text = str(data["error"])
        if _looks_like_missing_model(error_text):
            raise OllamaClientError(
                f"Le modele vision Ollama '{model}' n'est pas installe. Lance: ollama pull {model}"
            )
        raise OllamaClientError(f"Erreur Ollama vision: {error_text}")

    if not isinstance(data, dict):
        raise OllamaClientError("Ollama vision a renvoye une reponse inattendue.")

    content = data.get("message", {}).get("content", "").strip()
    if not content:
        raise OllamaClientError("Ollama vision n'a pas renvoye d'analyse exploitable.")

    return content

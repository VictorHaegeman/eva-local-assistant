import json
import re
from typing import Any, Literal, TypedDict

import httpx

from app.config import settings

GROQ_API_BASE = "https://api.groq.com/openai/v1"


class GroqClientError(Exception):
    """Raised when Eva cannot get a usable answer from Groq."""


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
            raise GroqClientError("Groq n'a pas renvoye de JSON exploitable.")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise GroqClientError("Groq a renvoye un JSON invalide.") from exc

    if not isinstance(data, dict):
        raise GroqClientError("Groq a renvoye un JSON inattendu.")
    return data


async def ask_groq(
    messages: list[ChatMessage],
    system_prompt: str,
    model: str | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
) -> str:
    selected_model = model or settings.groq_model
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "temperature": temperature if temperature is not None else settings.ollama_temperature,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(
            base_url=GROQ_API_BASE,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=timeout or settings.groq_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise GroqClientError("Impossible de contacter l'API Groq.") from exc
    except httpx.TimeoutException as exc:
        raise GroqClientError("L'API Groq ne repond pas dans le delai attendu.") from exc
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("error", {}).get("message", exc.response.text)
        except Exception:
            detail = exc.response.text
        raise GroqClientError(
            f"Groq a repondu avec HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise GroqClientError("Impossible de contacter correctement l'API Groq.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise GroqClientError("Groq a renvoye une reponse non JSON.") from exc

    content = (
        data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    )
    if not content:
        raise GroqClientError("Groq n'a pas renvoye de reponse exploitable.")
    return content


async def ask_groq_json(
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    timeout_seconds: float | None = None,
    temperature: float = 0.1,
) -> dict[str, Any]:
    selected_model = model or settings.groq_model
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "stream": False,
        "response_format": {"type": "json_object"},
    }

    try:
        async with httpx.AsyncClient(
            base_url=GROQ_API_BASE,
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=timeout_seconds or settings.groq_timeout_seconds,
        ) as client:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise GroqClientError("Impossible de contacter l'API Groq pour le JSON.") from exc
    except httpx.TimeoutException as exc:
        raise GroqClientError("Groq ne repond pas assez vite pour le JSON.") from exc
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("error", {}).get("message", exc.response.text)
        except Exception:
            detail = exc.response.text
        raise GroqClientError(
            f"Groq JSON a repondu avec HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        raise GroqClientError("Impossible de contacter l'API Groq pour le JSON.") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise GroqClientError("Groq JSON a renvoye une reponse non JSON.") from exc

    content = (
        data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    )
    if not content:
        raise GroqClientError("Groq JSON n'a pas renvoye de contenu exploitable.")
    return _extract_json_object(content)

"""Small Ollama client used by ``context-kit chat``.

Keeps the dependency footprint at zero by using the Python standard
library for the HTTP call.
"""

from __future__ import annotations

import json
import os
from urllib import error, request

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)


class OllamaError(RuntimeError):
    """Raised when the Ollama request fails or returns an invalid payload."""


def build_chat_payload(orientation: str, prompt: str, *, model: str) -> dict:
    return {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": orientation},
            {"role": "user", "content": prompt},
        ],
    }


def build_messages_payload(messages: list[dict[str, str]], *, model: str) -> dict:
    return {
        "model": model,
        "stream": False,
        "messages": messages,
    }


def chat(
    orientation: str,
    prompt: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 60.0,
) -> str:
    """Send ``orientation`` + ``prompt`` to Ollama and return the reply text."""
    payload = build_chat_payload(orientation, prompt, model=model or OLLAMA_MODEL)
    return _post_chat(payload, base_url=base_url, timeout=timeout)


def chat_messages(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 60.0,
) -> str:
    """Send a full message history to Ollama and return the reply text."""
    payload = build_messages_payload(messages, model=model or OLLAMA_MODEL)
    return _post_chat(payload, base_url=base_url, timeout=timeout)


def _post_chat(payload: dict, *, base_url: str | None, timeout: float) -> str:
    url = f"{(base_url or OLLAMA_BASE_URL).rstrip('/')}/api/chat"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise OllamaError(f"Ollama request failed with HTTP {exc.code}: {body or exc.reason}") from exc
    except error.URLError as exc:
        raise OllamaError(f"Could not reach Ollama at {url}: {exc.reason}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OllamaError("Ollama returned invalid JSON") from exc

    message = data.get("message")
    if not isinstance(message, dict):
        raise OllamaError("Ollama response missing message content")
    content = message.get("content")
    if not isinstance(content, str):
        raise OllamaError("Ollama response missing assistant text")
    return content

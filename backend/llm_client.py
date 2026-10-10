# Route JSON generation to verified, capability-matched LLM providers with fallback.
"""Small multi-provider JSON client used by all generation agents."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI

load_dotenv()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelChoice:
    """One model, its credential, and its OpenAI-compatible endpoint."""

    provider: str
    model: str
    key_name: str
    base_url: str | None = None


MODELS: dict[str, ModelChoice] = {
    "openrouter_coder": ModelChoice("OpenRouter", "qwen/qwen3-coder-flash", "OPENROUTER_API_KEY",
                                    "https://openrouter.ai/api/v1"),
    "groq_reasoning": ModelChoice("Groq", "openai/gpt-oss-120b", "GROQ_API_KEY",
                                  "https://api.groq.com/openai/v1"),
    "groq_cheap": ModelChoice("Groq", "openai/gpt-oss-20b", "GROQ_API_KEY",
                              "https://api.groq.com/openai/v1"),
    "nvidia_reasoning": ModelChoice("NVIDIA", "nvidia/nemotron-3-super-120b-a12b", "NVIDIA_API_KEY",
                                    "https://integrate.api.nvidia.com/v1"),
    "nvidia_cheap": ModelChoice("NVIDIA", "z-ai/glm-5.3-flash", "NVIDIA_API_KEY",
                                "https://integrate.api.nvidia.com/v1"),
    "gemini_fast": ModelChoice("Gemini", "gemini-2.5-flash", "GEMINI_API_KEY",
                               "https://generativelanguage.googleapis.com/v1beta/openai/"),
}

# Each row moves to the next configured provider after a transport, HTTP, or JSON failure.
ROUTES: dict[str, tuple[str, ...]] = {
    "requirements": ("groq_reasoning", "gemini_fast", "openrouter_coder", "nvidia_reasoning"),
    "architecture": ("groq_reasoning", "gemini_fast", "openrouter_coder", "nvidia_reasoning"),
    "coding": ("openrouter_coder", "groq_reasoning", "nvidia_reasoning", "gemini_fast"),
    "testing": ("groq_reasoning", "gemini_fast", "openrouter_coder",
                "nvidia_cheap", "nvidia_reasoning", "groq_cheap"),
    "repair": ("openrouter_coder", "groq_reasoning", "nvidia_reasoning", "gemini_fast"),
    "verification": ("groq_reasoning", "gemini_fast", "openrouter_coder", "nvidia_reasoning"),
    "explanation": ("groq_reasoning", "gemini_fast", "nvidia_reasoning", "openrouter_coder"),
    "cheap": ("groq_cheap", "gemini_fast", "nvidia_cheap", "openrouter_coder"),
    "general": ("groq_reasoning", "gemini_fast", "openrouter_coder", "nvidia_reasoning"),
}

_clients: dict[tuple[str, str], AsyncOpenAI] = {}
_unavailable_until: dict[str, float] = {}
TESTING_TOTAL_TIMEOUT = 45.0
TESTING_PROVIDER_TIMEOUT = 12.0
GENERATION_TOTAL_TIMEOUT = 120.0
GENERATION_PROVIDER_TIMEOUT = 28.0
REPAIR_TOTAL_TIMEOUT = 45.0
REPAIR_PROVIDER_TIMEOUT = 12.0
VERIFICATION_TOTAL_TIMEOUT = 45.0
VERIFICATION_PROVIDER_TIMEOUT = 12.0


def _parse_json_object(content: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating common markdown and prose wrappers."""
    candidates = [content.strip()]
    if candidates[0].startswith("```"):
        candidates.append(candidates[0].split("\n", 1)[-1].removesuffix("```").strip())
    start, end = content.find("{"), content.rfind("}")
    if start >= 0 and end > start:
        candidates.append(content[start:end + 1])

    for candidate in dict.fromkeys(candidates):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError("The model response did not contain a valid JSON object.")


def model_route(capability: str = "general", model: str | None = None) -> list[ModelChoice]:
    """Return configured models in capability order, preserving legacy OpenAI settings."""
    if capability not in ROUTES:
        raise ValueError(f"Unknown model capability: {capability}.")
    route = [MODELS[name] for name in ROUTES[capability]
             if os.getenv(MODELS[name].key_name, "").strip()
             and not os.getenv(MODELS[name].key_name, "").strip().lower().startswith("your_")]
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if openai_key and not openai_key.startswith("your_"):
        configured_model = model or os.getenv(
            "OPENAI_MODEL_CHEAP" if capability == "cheap" else "OPENAI_MODEL",
            "gpt-4o-mini" if capability == "cheap" else "gpt-4o",
        )
        openai_choice = ModelChoice("OpenAI", configured_model, "OPENAI_API_KEY")
        if model and model not in {"cheap", "general"}:
            route.insert(0, openai_choice)
        else:
            route.append(openai_choice)
    return route


def get_client(choice: ModelChoice) -> AsyncOpenAI:
    """Reuse one client per provider and credential without exposing its key."""
    key = os.getenv(choice.key_name, "").strip()
    identity = (choice.provider, key)
    if identity not in _clients:
        arguments: dict[str, Any] = {"api_key": key, "timeout": 40.0, "max_retries": 0}
        if choice.base_url:
            arguments["base_url"] = choice.base_url
        _clients[identity] = AsyncOpenAI(**arguments)
    return _clients[identity]


def _cooldown_seconds(error: Exception, capability: str = "general") -> int:
    """Avoid repeated slow requests to an unavailable provider."""
    if isinstance(error, APIStatusError):
        if error.status_code in {400, 401, 403, 404}:
            return 300
        if error.status_code == 429:
            return 60
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return 30 if capability != "repair" else 10
    return 15


async def generate_json(system: str, user: str, model: str | None = None,
                        capability: str | None = None,
                        validator: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Return a JSON object, trying the next suitable provider on any failed attempt."""
    selected_capability = capability or (
        "cheap" if model in {"cheap", os.getenv("OPENAI_MODEL_CHEAP", "gpt-4o-mini")}
        else "general"
    )
    candidates = model_route(selected_capability, model)
    if not candidates:
        raise RuntimeError("No LLM API key is configured. Add one supported provider key to .env.")
    attempted: list[str] = []
    if selected_capability == "testing":
        total_timeout, provider_timeout = TESTING_TOTAL_TIMEOUT, TESTING_PROVIDER_TIMEOUT
    elif selected_capability == "repair":
        total_timeout, provider_timeout = REPAIR_TOTAL_TIMEOUT, REPAIR_PROVIDER_TIMEOUT
    elif selected_capability == "verification":
        total_timeout, provider_timeout = VERIFICATION_TOTAL_TIMEOUT, VERIFICATION_PROVIDER_TIMEOUT
    else:
        total_timeout, provider_timeout = GENERATION_TOTAL_TIMEOUT, GENERATION_PROVIDER_TIMEOUT
    deadline = time.monotonic() + total_timeout
    for choice in candidates:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if (time.monotonic() < _unavailable_until.get(choice.provider, 0)
                or time.monotonic() < _unavailable_until.get(f"{choice.provider}/{choice.model}", 0)):
            continue
        try:
            arguments: dict[str, Any] = {
                "model": choice.model,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.2,
                "max_tokens": (2048 if selected_capability == "cheap" else
                               4096 if selected_capability == "testing" else 8192),
            }
            if choice.provider == "Groq":
                arguments["extra_body"] = {"reasoning_format": "hidden"}
            response = await asyncio.wait_for(
                get_client(choice).chat.completions.create(**arguments),
                timeout=min(provider_timeout, remaining),
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("The model returned no JSON content.")
            data = _parse_json_object(content)
            if validator is not None:
                validator(data)
            logger.info("LLM success: %s %s for %s", choice.provider, choice.model,
                        selected_capability)
            return data
        except (APIError, TimeoutError, ValueError, AttributeError, IndexError, KeyError, TypeError) as error:
            status_detail = (f" HTTP {error.status_code}"
                             if isinstance(error, APIStatusError) else "")
            attempted.append(
                f"{choice.provider}/{choice.model}: {type(error).__name__}{status_detail}")
            scope = (f"{choice.provider}/{choice.model}"
                     if isinstance(error, APIStatusError) and error.status_code in {400, 404}
                     else choice.provider)
            _unavailable_until[scope] = time.monotonic() + _cooldown_seconds(error, selected_capability)
            logger.warning("LLM fallback: %s %s failed for %s (%s)", choice.provider,
                           choice.model, selected_capability,
                           f"{type(error).__name__}{status_detail}")
    providers = ", ".join(attempted) or "all configured providers are cooling down"
    limit = f" within the {total_timeout:g}-second {selected_capability} limit"
    raise RuntimeError(f"No JSON-capable model is available for {selected_capability}{limit}: {providers}.")

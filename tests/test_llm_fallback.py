# Guard capability-based model ordering and automatic JSON fallback.
"""Deterministic tests for the shared multi-provider LLM router."""

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
from openai import BadRequestError
import httpx

from backend import llm_client


def test_model_routes_match_agent_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    """Coding and cheap explanations use distinct model orders."""
    for name in ("OPENROUTER_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert [item.provider for item in llm_client.model_route("coding")] == [
        "OpenRouter", "Groq", "NVIDIA", "Gemini"]
    assert [item.model for item in llm_client.model_route("cheap")] == [
        "openai/gpt-oss-20b", "gemini-2.5-flash", "z-ai/glm-5.3-flash",
        "qwen/qwen3-coder-flash"]


@pytest.mark.asyncio
async def test_invalid_json_falls_back_to_next_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The next configured provider supplies JSON after malformed model output."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm_client._unavailable_until.clear()
    calls: list[tuple[str, dict[str, Any]]] = []

    class Completion:
        """Return provider-specific content from a fake chat endpoint."""

        def __init__(self, provider: str) -> None:
            """Remember the provider selected by the router."""
            self.provider = provider

        async def create(self, **kwargs: Any) -> Any:
            """Record the request and simulate a malformed first response."""
            calls.append((self.provider, kwargs))
            content = "not JSON" if self.provider == "OpenRouter" else json.dumps({"ok": True})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def fake_client(choice: llm_client.ModelChoice) -> Any:
        """Provide a fake client with the same completion call shape."""
        return SimpleNamespace(chat=SimpleNamespace(completions=Completion(choice.provider)))

    monkeypatch.setattr(llm_client, "get_client", fake_client)
    try:
        result = await llm_client.generate_json("Return JSON.", "Check fallback.", capability="coding")
        assert result == {"ok": True}
        assert [provider for provider, _ in calls] == ["OpenRouter", "Groq"]
        assert calls[1][1]["extra_body"] == {"reasoning_format": "hidden"}
        assert calls[0][1]["response_format"] == {"type": "json_object"}
    finally:
        llm_client._unavailable_until.clear()


def test_json_parser_accepts_fenced_object_with_leading_prose() -> None:
    """Coding models may wrap an otherwise valid object in prose or markdown."""
    result = llm_client._parse_json_object(
        'Here are the requested files:\n```json\n{"main.py": "print(1)"}\n```'
    )
    assert result == {"main.py": "print(1)"}


@pytest.mark.asyncio
async def test_provider_http_status_is_included_in_fallback_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 400 fallback includes its HTTP code without logging provider response contents."""
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    for name in ("OPENROUTER_API_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    llm_client._unavailable_until.clear()

    class Completion:
        async def create(self, **kwargs: Any) -> Any:
            request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
            response = httpx.Response(400, request=request)
            raise BadRequestError("bad request", response=response, body={"secret": "omit"})

    monkeypatch.setattr(llm_client, "get_client", lambda choice: SimpleNamespace(
        chat=SimpleNamespace(completions=Completion())))
    try:
        with pytest.raises(RuntimeError, match=r"Groq/openai/gpt-oss-120b: BadRequestError HTTP 400") as exc:
            await llm_client.generate_json("JSON", "coding", capability="coding")
        assert "omit" not in str(exc.value)
    finally:
        llm_client._unavailable_until.clear()


@pytest.mark.asyncio
async def test_coding_provider_timeouts_are_bounded_and_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow coding provider is timed out quickly so the next provider can answer."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    for name in ("NVIDIA_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(llm_client, "GENERATION_PROVIDER_TIMEOUT", 0.02)
    monkeypatch.setattr(llm_client, "GENERATION_TOTAL_TIMEOUT", 0.1)
    llm_client._unavailable_until.clear()
    providers: list[str] = []

    class Completion:
        def __init__(self, provider: str) -> None:
            self.provider = provider

        async def create(self, **kwargs: Any) -> Any:
            providers.append(self.provider)
            if self.provider == "OpenRouter":
                await asyncio.sleep(1)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))])

    monkeypatch.setattr(llm_client, "get_client", lambda choice: SimpleNamespace(
        chat=SimpleNamespace(completions=Completion(choice.provider))))
    try:
        result = await asyncio.wait_for(
            llm_client.generate_json("JSON", "coding", capability="coding"), timeout=0.2,
        )
        assert result == {"ok": True}
        assert providers == ["OpenRouter", "Groq"]
    finally:
        llm_client._unavailable_until.clear()


@pytest.mark.asyncio
async def test_no_configured_model_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing provider configuration reports an actionable error."""
    for name in ("OPENROUTER_API_KEY", "GROQ_API_KEY", "NVIDIA_API_KEY",
                 "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="No LLM API key is configured"):
        await llm_client.generate_json("Return JSON.", "Hello.", capability="general")


@pytest.mark.asyncio
async def test_schema_validation_falls_back_to_next_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid JSON that breaks an agent contract triggers provider fallback."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    llm_client._unavailable_until.clear()
    providers: list[str] = []

    class Completion:
        """Return an incomplete object followed by a complete one."""

        def __init__(self, provider: str) -> None:
            """Remember which provider was selected."""
            self.provider = provider

        async def create(self, **kwargs: Any) -> Any:
            """Return a parseable object with provider-specific fields."""
            providers.append(self.provider)
            content = '{"ok": false}' if self.provider == "OpenRouter" else '{"ok": true}'
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def fake_client(choice: llm_client.ModelChoice) -> Any:
        """Serve the fake completion for the requested provider."""
        return SimpleNamespace(chat=SimpleNamespace(completions=Completion(choice.provider)))

    def require_success(data: dict[str, Any]) -> None:
        """Reject objects that violate the caller's contract."""
        if data.get("ok") is not True:
            raise ValueError("Expected a successful result.")

    monkeypatch.setattr(llm_client, "get_client", fake_client)
    try:
        result = await llm_client.generate_json(
            "Return JSON.", "Check fallback.", capability="coding", validator=require_success,
        )
        assert result == {"ok": True}
        assert providers == ["OpenRouter", "Groq"]
    finally:
        llm_client._unavailable_until.clear()


@pytest.mark.asyncio
async def test_test_writer_route_has_a_hard_time_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hung provider cannot leave Test Writer waiting indefinitely."""
    choice = llm_client.ModelChoice("Hung", "slow-test-model", "HUNG_API_KEY")
    monkeypatch.setattr(llm_client, "model_route", lambda *args: [choice])
    monkeypatch.setattr(llm_client, "TESTING_TOTAL_TIMEOUT", 0.05)
    monkeypatch.setattr(llm_client, "TESTING_PROVIDER_TIMEOUT", 0.02)
    llm_client._unavailable_until.clear()

    class Completion:
        """Simulate a provider that never responds within the test deadline."""

        async def create(self, **kwargs: Any) -> Any:
            """Wait longer than the router's configured provider limit."""
            await asyncio.sleep(1)
            return {}

    monkeypatch.setattr(llm_client, "get_client", lambda choice: SimpleNamespace(
        chat=SimpleNamespace(completions=Completion())))
    try:
        with pytest.raises(RuntimeError, match="testing limit"):
            await asyncio.wait_for(
                llm_client.generate_json("JSON", "tests", capability="testing"), timeout=0.2,
            )
    finally:
        llm_client._unavailable_until.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", ["repair", "verification"])
async def test_repair_and_verification_routes_use_short_time_limits(
    monkeypatch: pytest.MonkeyPatch, capability: str,
) -> None:
    """Healing and verification model outages cannot stall a build for two minutes."""
    choice = llm_client.ModelChoice("Hung", "slow-model", "HUNG_API_KEY")
    monkeypatch.setattr(llm_client, "model_route", lambda *args: [choice])
    monkeypatch.setattr(llm_client, f"{capability.upper()}_TOTAL_TIMEOUT", 0.05)
    monkeypatch.setattr(llm_client, f"{capability.upper()}_PROVIDER_TIMEOUT", 0.02)
    llm_client._unavailable_until.clear()

    class Completion:
        async def create(self, **kwargs: Any) -> Any:
            await asyncio.sleep(1)
            return {}

    monkeypatch.setattr(llm_client, "get_client", lambda choice: SimpleNamespace(
        chat=SimpleNamespace(completions=Completion())))
    try:
        with pytest.raises(RuntimeError, match=f"{capability} limit"):
            await asyncio.wait_for(
                llm_client.generate_json("JSON", "task", capability=capability), timeout=0.2,
            )
    finally:
        llm_client._unavailable_until.clear()

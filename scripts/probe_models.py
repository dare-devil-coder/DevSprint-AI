# Inspect configured provider model catalogs without exposing API credentials.
"""Read-only model availability probe for the four configured LLM providers."""

from __future__ import annotations

import json
import asyncio
import ast
import logging
import os
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values


def show_models(provider: str, url: str, key: str, header: str = "Authorization") -> None:
    """Report catalog status and model IDs without printing response bodies."""
    auth = f"Bearer {key}" if header == "Authorization" else key
    try:
        response = httpx.get(url, headers={header: auth}, timeout=20)
        print(f"{provider}: HTTP {response.status_code}")
        if response.status_code != 200:
            return
        payload: dict[str, Any] = response.json()
        models = payload.get("models", payload.get("data", []))
        print(f"  listed: {len(models)}")
        ids = [str(item.get("id", item.get("name", ""))).removeprefix("models/")
               for item in models if isinstance(item, dict)]
        terms = ("gemini-", "gpt-oss", "llama-3.3", "qwen3-coder", "qwen3.8",
                 "deepseek-v3", "nemotron-3", "claude-sonnet", "gpt-4o")
        for model_id in ids:
            if (provider == "NVIDIA" or provider == "Groq" or
                    ((provider != "OpenRouter" or ":free" in model_id or "coder" in model_id
                      or "sonnet" in model_id) and any(term in model_id.lower() for term in terms)
                     and "embed" not in model_id.lower())):
                print(f"  {model_id}")
    except (httpx.HTTPError, ValueError, TypeError) as error:
        print(f"{provider}: {type(error).__name__}")


def test_generation(provider: str, url: str, key: str, model: str) -> None:
    """Make one small JSON completion and report only its validity and status."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only a JSON object with the key ok set to true."},
            {"role": "user", "content": "Confirm that JSON generation works."},
        ],
        "max_tokens": 128,
        "response_format": {"type": "json_object"},
    }
    if provider == "Groq":
        payload["reasoning_format"] = "hidden"
    try:
        response = httpx.post(
            url, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=35,
        )
        valid = False
        detail = ""
        if response.status_code == 200:
            choice = response.json()["choices"][0]
            content = choice["message"].get("content")
            detail = f", finish={choice.get('finish_reason')}, content={type(content).__name__}"
            if isinstance(content, str):
                try:
                    valid = isinstance(json.loads(content), dict)
                except json.JSONDecodeError:
                    detail += f", raw_prefix={content[:80]!r}"
        else:
            body = response.json()
            error = body.get("error", {}) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                detail = f", error={str(error.get('message', error.get('code', '')))[:160]}"
        print(f"{provider} {model}: HTTP {response.status_code}, JSON object: {valid}{detail}")
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
        print(f"{provider} {model}: {type(error).__name__}")


def main() -> None:
    """Check the catalog endpoints for keys supplied in the private .env."""
    config = dotenv_values(".env")
    if "--coding-smoke" in sys.argv:
        from backend.llm_client import generate_json

        async def check_coding() -> None:
            """Check that the coding route returns two parseable Python files."""
            result = await generate_json(
                "Return only a JSON object with main.py and test_main.py as full Python source strings. "
                "main.py must define convert(celsius) returning Fahrenheit. test_main.py must "
                "contain a pytest test for zero Celsius. Use standard library in main.py.",
                "Build a small Celsius-to-Fahrenheit CLI. Input 0 must output 32.",
                capability="coding",
            )
            valid = all(isinstance(result.get(name), str) and result[name].strip()
                        for name in ("main.py", "test_main.py"))
            if valid:
                ast.parse(result["main.py"])
                ast.parse(result["test_main.py"])
            print(f"coding smoke: two parseable Python files={bool(valid)}")

        asyncio.run(check_coding())
        return
    if "--serpapi" in sys.argv:
        from backend import serpapi_client

        key = config.get("SERPAPI_API_KEY")
        if not key:
            print("SerpApi: no key configured")
            return
        with TemporaryDirectory(prefix="devsprint-serpapi-check-") as location:
            serpapi_client.SERPAPI_CACHE_FILE = Path(location) / "cache.json"
            serpapi_client.SERPAPI_LOG_FILE = Path(location) / "log.json"
            os.environ["SERPAPI_API_KEY"] = key
            try:
                results = serpapi_client.search_for_fix(
                    "ModuleNotFoundError: No module named pytest", "python")
                print(f"SerpApi: live search succeeded, results={len(results)}")
            except (RuntimeError, ValueError) as error:
                reason = str(error).replace(key, "[redacted]")[:180]
                print(f"SerpApi: live search failed ({type(error).__name__}: {reason})")
        return
    if "--fallback" in sys.argv:
        from backend import llm_client

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        original = {name: os.environ.get(name) for name in
                    ("OPENROUTER_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY")}

        async def check_fallback() -> None:
            """Verify that bad credentials lead to a working next provider."""
            scenarios = (
                ("requirements", ("GROQ_API_KEY",)),
                ("coding", ("OPENROUTER_API_KEY", "GROQ_API_KEY")),
                ("cheap", ("GROQ_API_KEY", "GEMINI_API_KEY")),
            )
            try:
                for capability, disabled in scenarios:
                    llm_client._unavailable_until.clear()
                    for name, value in original.items():
                        if value is None:
                            os.environ.pop(name, None)
                        else:
                            os.environ[name] = value
                    for name in disabled:
                        os.environ[name] = "invalid-probe-key"
                    result = await llm_client.generate_json(
                        "Return JSON with the boolean key ok set to true.",
                        "Confirm fallback JSON generation.", capability=capability,
                    )
                    print(f"{capability} fallback: valid JSON object={result.get('ok') is True}")
            finally:
                for name, value in original.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value
                llm_client._unavailable_until.clear()

        asyncio.run(check_fallback())
        return
    if "--router" in sys.argv:
        from backend.llm_client import generate_json

        async def check_routes() -> None:
            """Exercise the production router with one small JSON request per tier."""
            for capability in ("requirements", "coding", "cheap"):
                try:
                    result = await generate_json(
                        "Return JSON with the boolean key ok set to true.",
                        "Confirm this provider can generate JSON.", capability=capability,
                    )
                    print(f"{capability}: valid JSON object={result.get('ok') is True}")
                except RuntimeError as error:
                    print(f"{capability}: {error}")

        asyncio.run(check_routes())
        return
    if "--nvidia" in sys.argv:
        key = config.get("NVIDIA_API_KEY")
        if key:
            for model in ("z-ai/glm-5.3-flash", "google/gemma-4-31b-it",
                          "nvidia/nemotron-3-super-120b-a12b", "mistralai/mistral-large-2-instruct"):
                test_generation("NVIDIA", "https://integrate.api.nvidia.com/v1/chat/completions", key, model)
        return
    if "--tiers" in sys.argv:
        candidates = (
            ("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-pro"),
            ("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash-lite"),
            ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-20b"),
        )
        for name, env_name, url, model in candidates:
            key = config.get(env_name)
            if key:
                test_generation(name, url, key, model)
        return
    if "--live" in sys.argv:
        candidates = (
            ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions", "qwen/qwen3-coder-flash"),
            ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions", "openai/gpt-oss-120b"),
            ("NVIDIA", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1/chat/completions", "nvidia/nemotron-3-super-120b-a12b"),
            ("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
        )
        for name, env_name, url, model in candidates:
            key = config.get(env_name)
            if key:
                test_generation(name, url, key, model)
        return
    providers = (
        ("OpenRouter", "https://openrouter.ai/api/v1/models", "OPENROUTER_API_KEY", "Authorization"),
        ("Groq", "https://api.groq.com/openai/v1/models", "GROQ_API_KEY", "Authorization"),
        ("NVIDIA", "https://integrate.api.nvidia.com/v1/models", "NVIDIA_API_KEY", "Authorization"),
        ("Gemini", "https://generativelanguage.googleapis.com/v1beta/models", "GEMINI_API_KEY", "x-goog-api-key"),
    )
    for name, url, env_name, header in providers:
        key = config.get(env_name)
        if key:
            show_models(name, url, key, header)
        else:
            print(f"{name}: no key configured")


if __name__ == "__main__":
    main()

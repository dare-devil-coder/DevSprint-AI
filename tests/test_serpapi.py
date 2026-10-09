# Verify cached SerpApi calls and the durable proof log without network access.

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import serpapi_client
from backend.memory import shared_memory


def test_search_logs_network_and_cache_hits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """One network lookup and one cache hit should produce two audit entries."""
    calls = []

    class FakeClient:
        """Stand in for the SerpApi package client."""

        def __init__(self, api_key: str) -> None:
            """Capture the provided key without making a network request."""
            assert api_key == "test-key"

        def search(self, params: dict) -> dict:
            """Return one organic search result."""
            calls.append(params)
            return {"organic_results": [{"title": "Fix", "snippet": "Use the right import",
                                          "link": "https://example.test/fix"}]}

    monkeypatch.setitem(sys.modules, "serpapi", SimpleNamespace(Client=FakeClient))
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    cache = tmp_path / "cache.json"
    log = tmp_path / "log.json"
    monkeypatch.setattr(serpapi_client, "SERPAPI_CACHE_FILE", cache)
    monkeypatch.setattr(serpapi_client, "SERPAPI_LOG_FILE", log)
    first = serpapi_client.search_for_fix("ModuleNotFoundError: sample", "python")
    second = serpapi_client.search_for_fix("ModuleNotFoundError: sample", "python")
    assert first == second
    assert len(calls) == 1
    entries = shared_memory.read_json(log)["calls"]
    assert [entry["cached"] for entry in entries] == [False, True]
    assert all(entry["results_count"] == 1 for entry in entries)


def test_rate_limit_retries_once_and_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 429 should wait once, retry, and retain one audit record."""
    attempts = []

    class RateLimitError(Exception):
        """A fake service response carrying the 429 status."""

        status_code = 429

    class FakeClient:
        """Return a rate limit once, then a valid result."""

        def __init__(self, api_key: str) -> None:
            """Accept a nonempty test credential."""
            assert api_key == "test-key"

        def search(self, params: dict) -> dict:
            """Count service requests and succeed on the second request."""
            attempts.append(params)
            if len(attempts) == 1:
                raise RateLimitError("429")
            return {"organic_results": [{"title": "Docs", "snippet": "Current API",
                                          "link": "https://example.test/docs"}]}

    monkeypatch.setitem(sys.modules, "serpapi", SimpleNamespace(Client=FakeClient))
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    monkeypatch.setattr(serpapi_client, "SERPAPI_CACHE_FILE", tmp_path / "cache.json")
    log = tmp_path / "log.json"
    monkeypatch.setattr(serpapi_client, "SERPAPI_LOG_FILE", log)
    monkeypatch.setattr(serpapi_client.time, "sleep", lambda seconds: None)
    result = serpapi_client.search_for_docs("fastapi", "routing")
    assert result == ["Current API"]
    assert len(attempts) == 2
    assert shared_memory.read_json(log)["calls"][0]["results_count"] == 1

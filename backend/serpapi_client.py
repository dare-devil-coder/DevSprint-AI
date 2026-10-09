# Cached SerpApi searches with a durable record of every lookup.
"""Cached SerpApi searches with a durable record of every lookup."""

import hashlib
import os
import time
from datetime import datetime, timezone
from typing import Any

from backend.memory.shared_memory import (
    SERPAPI_CACHE_FILE, SERPAPI_LOG_FILE, append_json_list, read_json, write_json,
)


def _search(query: str, count: int, error_context: str) -> list[dict[str, str]]:
    """Search once, retry a 429 once, and log even failed lookups."""
    digest = hashlib.md5(query.encode("utf-8")).hexdigest()
    cache = read_json(SERPAPI_CACHE_FILE)
    cached = digest in cache
    results: list[dict[str, str]] = cache.get(digest, [])
    failure = ""
    if not cached:
        key = os.getenv("SERPAPI_API_KEY", "").strip()
        if not key or key == "your_serpapi_key_here":
            failure = "SERPAPI_API_KEY is missing. Add it to .env to search for fixes."
        else:
            for attempt in range(2):
                try:
                    import serpapi

                    response: dict[str, Any] = serpapi.Client(api_key=key).search(
                        {"engine": "google", "q": query, "num": count}
                    )
                    if response.get("error"):
                        raise RuntimeError(str(response["error"]))
                    results = [{"title": str(item.get("title", "")),
                                "snippet": str(item.get("snippet", "")),
                                "link": str(item.get("link", ""))}
                               for item in response.get("organic_results", [])[:count]]
                    cache[digest] = results
                    write_json(SERPAPI_CACHE_FILE, cache)
                    failure = ""
                    break
                except Exception as exc:
                    failure = str(exc)
                    if attempt == 0 and (getattr(exc, "status_code", None) == 429 or "429" in failure):
                        time.sleep(2)
                        continue
                    break
    append_json_list(SERPAPI_LOG_FILE, {
        "timestamp": datetime.now(timezone.utc).isoformat(), "query": query,
        "results_count": len(results), "cached": cached, "agent": "self_healing_agent",
        "error_context": error_context, "error": failure,
    }, key="calls")
    if failure:
        raise RuntimeError(failure)
    return results


def search_for_fix(error_message: str, language: str) -> list[dict[str, str]]:
    """Find three relevant public fixes for one execution error."""
    compact = " ".join(error_message.split())[:180]
    return _search(f"{language} {compact} fix", 3, error_message)


def search_for_docs(library: str, topic: str) -> list[str]:
    """Find current documentation snippets for a library topic."""
    return [item["snippet"] for item in _search(f"{library} {topic} documentation", 2, topic)]

# SerpApi Usage in DevSprint AI

## Why SerpApi Matters Here
LLMs hallucinate outdated APIs. When the self-healing loop fixes code, it
guesses. SerpApi replaces guessing with fact-based fixes.

## Integration Point
SerpApi is called ONLY inside self_healing_agent.py. The flow:

  1. Executor Agent runs code -> error occurs
  2. Executor writes error to memory/errors.json
  3. Self-Healing Agent reads error
  4. Self-Healing Agent extracts: error type, library name, language
  5. Self-Healing Agent calls serpapi_client.search_for_fix(error, language)
  6. SerpApi returns top 3 Google results with snippets
  7. Self-Healing Agent passes snippets + error + code to LLM
  8. LLM produces fix based on current, search-verified information
  9. Self-Healing Agent writes fix to code, writes search results to
     memory/fixes.json
 10. Executor Agent runs again

## Exact SerpApi Call

```python
import os
import json
import hashlib
import serpapi

SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
client = serpapi.Client(api_key=SERPAPI_KEY)

CACHE_FILE = "memory/serpapi_cache.json"
LOG_FILE = "memory/serpapi_log.json"


def _load_cache() -> dict:
    """Load the SerpApi query cache from disk."""
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def _save_cache(cache: dict) -> None:
    """Persist the SerpApi query cache to disk."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def _log_call(query: str, results_count: int, cached: bool, error_context: str) -> None:
    """Append a SerpApi call record to the log file (hackathon proof)."""
    try:
        with open(LOG_FILE) as f:
            log = json.load(f)
    except FileNotFoundError:
        log = {"calls": []}

    log["calls"].append({
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "query": query,
        "results_count": results_count,
        "cached": cached,
        "agent": "self_healing_agent",
        "error_context": error_context,
    })

    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def search_for_fix(error_message: str, language: str) -> list:
    """
    Search Google for a fix to a code error.
    Results are cached by query hash to avoid duplicate API calls.
    """
    query = f"{language} {error_message[:100]} fix"
    cache_key = hashlib.md5(query.encode()).hexdigest()
    cache = _load_cache()

    if cache_key in cache:
        _log_call(query, len(cache[cache_key]), True, error_message)
        return cache[cache_key]

    results = client.search({
        "engine": "google",
        "q": query,
        "num": 3,
    })

    snippets = []
    for result in results.get("organic_results", [])[:3]:
        snippets.append({
            "title": result.get("title", ""),
            "snippet": result.get("snippet", ""),
            "link": result.get("link", ""),
        })

    cache[cache_key] = snippets
    _save_cache(cache)
    _log_call(query, len(snippets), False, error_message)
    return snippets


def search_for_docs(library: str, topic: str) -> list:
    """Search for current library documentation."""
    query = f"{library} {topic} documentation"
    cache_key = hashlib.md5(query.encode()).hexdigest()
    cache = _load_cache()

    if cache_key in cache:
        _log_call(query, len(cache[cache_key]), True, topic)
        return cache[cache_key]

    results = client.search({
        "engine": "google",
        "q": query,
        "num": 2,
    })

    snippets = [r.get("snippet", "") for r in results.get("organic_results", [])[:2]]
    cache[cache_key] = snippets
    _save_cache(cache)
    _log_call(query, len(snippets), False, topic)
    return snippets
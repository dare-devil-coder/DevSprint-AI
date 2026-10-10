# Atomic JSON files shared by the DevSprint agents.
"""Atomic JSON files shared by the DevSprint agents."""

import json
import os
import tempfile
import time
from pathlib import Path
from threading import RLock
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT / "memory"
WORKSPACE_DIR = ROOT / "workspace"
PROJECT_FILE = MEMORY_DIR / "project.json"
CONTRACT_FILE = MEMORY_DIR / "contract.json"
ERRORS_FILE = MEMORY_DIR / "errors.json"
FIXES_FILE = MEMORY_DIR / "fixes.json"
SERPAPI_CACHE_FILE = MEMORY_DIR / "serpapi_cache.json"
SERPAPI_LOG_FILE = MEMORY_DIR / "serpapi_log.json"
OUTPUT_FILE = MEMORY_DIR / "output.json"
PLAN_FILE = MEMORY_DIR / "plan.json"
VERIFICATION_FILE = MEMORY_DIR / "verification.json"
DECISIONS_FILE = MEMORY_DIR / "decisions.json"
PROJECT_DETAILS_CACHE_FILE = MEMORY_DIR / "project_details_cache.json"
SETTINGS_FILE = MEMORY_DIR / "settings.json"
_lock = RLock()


def read_json(path: str | Path, default: Any = None) -> Any:
    """Read JSON; treat an absent or empty scaffold file as its default."""
    target = Path(path)
    with _lock:
        if not target.exists() or target.stat().st_size == 0:
            return {} if default is None else default
        with target.open(encoding="utf-8") as stream:
            return json.load(stream)


def write_json(path: str | Path, data: Any) -> None:
    """Replace a JSON file atomically so readers never see partial content."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        descriptor, temporary = tempfile.mkstemp(dir=target.parent, suffix=".json.tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
            for attempt in range(6):
                try:
                    os.replace(temporary, target)
                    break
                except PermissionError:
                    if attempt == 5:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def append_json_list(path: str | Path, item: dict, key: str | None = None) -> None:
    """Append a record to a JSON list, optionally inside a named object key."""
    with _lock:
        data = read_json(path, {key: []} if key else [])
        if key:
            data.setdefault(key, []).append(item)
        else:
            data.append(item)
        write_json(path, data)

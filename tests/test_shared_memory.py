# Verify atomic JSON storage recovers from short Windows file-sharing locks.
"""Regression checks for transient Windows replacement failures."""

from pathlib import Path

import pytest

from backend.memory import shared_memory


def test_write_json_retries_transient_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two brief sharing violations do not stop a saved pipeline transition."""
    target = tmp_path / "project.json"
    original_replace = shared_memory.os.replace
    calls = 0

    def locked_replace(source: str | Path, destination: str | Path) -> None:
        """Simulate a short lived external reader holding the destination."""
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError(5, "Access is denied", str(destination))
        original_replace(source, destination)

    monkeypatch.setattr(shared_memory.os, "replace", locked_replace)
    monkeypatch.setattr(shared_memory.time, "sleep", lambda duration: None)
    shared_memory.write_json(target, {"phase": "building"})
    assert calls == 3
    assert shared_memory.read_json(target) == {"phase": "building"}

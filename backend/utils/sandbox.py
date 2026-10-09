# Run generated Python in a bounded local subprocess.
"""Run generated Python in a bounded local subprocess."""

import os
import subprocess
import sys
from pathlib import Path


def run_python(file_path: str, cwd: str, timeout: int = 30) -> dict:
    """Run one Python file with captured output and a time limit."""
    try:
        completed = subprocess.run(
            [sys.executable, "-I", file_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            input="",
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        return {
            "success": completed.returncode == 0,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "stdout": (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            "stderr": f"Execution timed out after {timeout} seconds.",
            "exit_code": -1,
        }
    except OSError as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "exit_code": -1}


def run_tests(cwd: Path, timeout: int) -> dict:
    """Run generated tests with pytest when a test file exists."""
    if not (cwd / "test_main.py").exists():
        return {"success": True, "stdout": "No test file was generated.", "stderr": "", "exit_code": 0}
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "test_main.py"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
            input="",
        )
        return {"success": completed.returncode == 0, "stdout": completed.stdout,
                "stderr": completed.stderr, "exit_code": completed.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Tests timed out after {timeout} seconds.", "exit_code": -1}

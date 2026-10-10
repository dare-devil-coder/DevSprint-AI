# Run generated Python in a bounded local subprocess.
"""Run generated Python in a bounded local subprocess."""

import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path


def run_python(file_path: str, cwd: str, timeout: int = 30,
               arguments: tuple[str, ...] = ()) -> dict:
    """Run one Python file with bounded arguments, output capture, and a time limit."""
    try:
        completed = subprocess.run(
            [sys.executable, "-I", file_path, *arguments],
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
    isolated_config = None
    config_arg: list[str] = []
    if not any((cwd / name).is_file() for name in ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")):
        # Prevent pytest from inheriting DevSprint's config from a parent workspace folder.
        isolated_config = cwd / ".devsprint-pytest.ini"
        isolated_config.write_text("[pytest]\n", encoding="utf-8")
        config_arg = ["-c", isolated_config.name]
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *config_arg, "test_main.py"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
            input="",
            # A generated project's tests are intentionally self-contained. Loading
            # unrelated global pytest plugins can add network hooks and stall execution.
            env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        )
        return {"success": completed.returncode == 0, "stdout": completed.stdout,
                "stderr": completed.stderr, "exit_code": completed.returncode}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Tests timed out after {timeout} seconds.", "exit_code": -1}
    finally:
        if isolated_config:
            isolated_config.unlink(missing_ok=True)


class _PrototypeParser(HTMLParser):
    """Collect the semantic landmarks and local assets of one generated page."""

    def __init__(self) -> None:
        """Initialize observed tags and local resource links."""
        super().__init__(convert_charrefs=True)
        self.tags: set[str] = set()
        self.styles: set[str] = set()
        self.scripts: set[str] = set()
        self.has_doctype = False

    def handle_decl(self, decl: str) -> None:
        """Remember that the page declares an HTML document type."""
        self.has_doctype = decl.casefold().strip() == "doctype html"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Record semantic elements and approved local browser assets."""
        self.tags.add(tag.casefold())
        values = {name.casefold(): (value or "") for name, value in attrs}
        if tag.casefold() == "link" and "stylesheet" in values.get("rel", "").casefold():
            self.styles.add(values.get("href", ""))
        if tag.casefold() == "script":
            self.scripts.add(values.get("src", ""))


def run_web_checks(cwd: Path, timeout: int = 15) -> dict:
    """Check prototype structure, local assets, CSS balance, and JS syntax when Node exists."""
    required = ("index.html", "styles.css", "app.js")
    missing = [name for name in required if not (cwd / name).is_file()]
    if missing:
        return {"success": False, "stdout": "", "stderr":
                "Missing prototype files: " + ", ".join(missing), "exit_code": 1}
    html = (cwd / "index.html").read_text(encoding="utf-8")
    css = (cwd / "styles.css").read_text(encoding="utf-8")
    js = (cwd / "app.js").read_text(encoding="utf-8")
    parser = _PrototypeParser()
    parser.feed(html)
    if not parser.has_doctype:
        return {"success": False, "stdout": "", "stderr":
                "Prototype HTML must declare <!doctype html>.", "exit_code": 1}
    required_tags = {"html", "head", "title", "body", "main"}
    missing_tags = required_tags - parser.tags
    if missing_tags:
        return {"success": False, "stdout": "", "stderr":
                "Missing semantic HTML structure: " + ", ".join(sorted(missing_tags)),
                "exit_code": 1}
    if "styles.css" not in parser.styles or "app.js" not in parser.scripts:
        return {"success": False, "stdout": "", "stderr":
                "index.html must load local styles.css and app.js.", "exit_code": 1}
    if re.search(r"<script[^>]+src=[\"']https?://|<link[^>]+href=[\"']https?://", html, re.I):
        return {"success": False, "stdout": "", "stderr":
                "Prototype assets must be local; remote scripts and styles are blocked.",
                "exit_code": 1}
    if css.count("{") != css.count("}"):
        return {"success": False, "stdout": "", "stderr": "Prototype CSS has unbalanced braces.",
                "exit_code": 1}
    output = ["HTML landmarks and local CSS/JavaScript assets passed."]
    node = shutil.which("node")
    if node:
        try:
            checked = subprocess.run([node, "--check", "app.js"], cwd=str(cwd),
                                     capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr":
                    f"JavaScript syntax check timed out after {timeout} seconds.", "exit_code": -1}
        if checked.returncode:
            return {"success": False, "stdout": checked.stdout,
                    "stderr": checked.stderr or "JavaScript syntax check failed.",
                    "exit_code": checked.returncode}
        output.append("JavaScript syntax check passed.")
    else:
        output.append("Node.js is unavailable; JavaScript syntax will be exercised in the browser preview.")
    return {"success": True, "stdout": "\n".join(output), "stderr": "", "exit_code": 0}

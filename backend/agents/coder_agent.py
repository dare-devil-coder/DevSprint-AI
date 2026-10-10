# Generate the main program and its tests from the project contract.
"""Generate the main program and its tests from the project contract."""

import ast
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, PLAN_FILE, WORKSPACE_DIR, read_json


def source_files_for_type(project_type: str) -> list[str]:
    """Return the source files allowed for a supported project type."""
    if project_type == "web_app":
        return ["index.html", "styles.css", "app.js"]
    if project_type == "python_cli":
        return ["main.py", "test_main.py"]
    raise ValueError("The project type must be web_app or python_cli.")


def validate_code_files(files: dict[str, Any], project_type: str = "python_cli") -> None:
    """Reject incomplete, unsafe, or syntactically invalid generated source files."""
    source_names = source_files_for_type(project_type)
    required = source_names
    if not all(isinstance(files.get(name), str) and files[name].strip() for name in required):
        raise ValueError(f"The model must return nonempty files: {', '.join(required)}.")
    if set(files) != set(required):
        raise ValueError("The model returned files outside the approved project structure.")
    if project_type == "python_cli":
        for name in required:
            try:
                ast.parse(files[name], filename=name)
            except SyntaxError as exc:
                raise ValueError(f"Generated {name} has invalid Python syntax: {exc}") from exc
        return
    html = files["index.html"]
    for marker in ("<!doctype html", "<title", "name=\"viewport\"", "<main", "styles.css", "app.js"):
        if marker.casefold() not in html.casefold():
            raise ValueError(f"Generated web prototype is missing {marker}.")
    if re.search(r"<script[^>]+src=[\"']https?://|<link[^>]+href=[\"']https?://", html, re.I):
        raise ValueError("The prototype must not depend on remote scripts or stylesheets.")
    if re.search(r"@import|url\(\s*[\"']?https?://", files["styles.css"], re.I):
        raise ValueError("The prototype stylesheet must not load remote resources.")
    if re.search(r"^\s*import\s|\bimport\s*\(", files["app.js"], re.M):
        raise ValueError("The prototype JavaScript must be self-contained.")
    node = shutil.which("node")
    if node:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as stream:
            stream.write(files["app.js"])
            temporary_path = stream.name
        try:
            checked = subprocess.run([node, "--check", temporary_path], capture_output=True,
                                     text=True, timeout=5, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ValueError("Generated JavaScript syntax checking exceeded 5 seconds.") from exc
        finally:
            Path(temporary_path).unlink(missing_ok=True)
        if checked.returncode:
            detail = checked.stderr.strip().splitlines()[-1] if checked.stderr.strip() else "invalid syntax"
            raise ValueError(f"Generated app.js has invalid JavaScript syntax: {detail}")


def write_code_files(project_name: str, files: dict[str, Any],
                     project_type: str = "python_cli") -> list[str]:
    """Validate and write only source files approved for this project type."""
    validate_code_files(files, project_type)
    root = WORKSPACE_DIR / project_name
    root.mkdir(parents=True, exist_ok=True)
    for name in source_files_for_type(project_type):
        (root / name).write_text(files[name], encoding="utf-8")
    return [f"{project_name}/{name}" for name in source_files_for_type(project_type)]


class CoderAgent(BaseAgent):
    """Build either the requested Python CLI or a complete browser prototype."""

    def __init__(self) -> None:
        """Name the coding agent."""
        super().__init__("Coder", "coder")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist code from the saved contract."""
        contract = context["memory"]["contract"] if "memory" in context else read_json(CONTRACT_FILE)
        plan = context["memory"]["plan"] if "memory" in context else read_json(PLAN_FILE)
        project_type = contract.get("project_type", "python_cli")
        gaps = context.get("gaps", [])

        if project_type == "web_app":
            instruction = (
                "Return only a JSON object with exactly index.html, styles.css, and app.js; each value is a full source string. "
                "Build a finished, polished, responsive, accessible browser prototype from the approved contract and plan. "
                "Implement every requested screen, interaction, and acceptance criterion; make buttons, forms, navigation, "
                "validation, empty states, and feedback actually work. Use semantic HTML, keyboard support, responsive CSS, "
                "and vanilla JavaScript. Use in-memory demo data only. Do not add remote scripts, stylesheets, fonts, images, "
                "frameworks, API calls, authentication claims, or unrequested features. Include a clear page title, viewport "
                "meta tag, and main landmark. Link styles.css and app.js from index.html. Keep project-specific copy and "
                "design_direction from the contract. If verification gaps are supplied, repair them without removing "
                "already-working behavior. No markdown fences or extra files."
            )
            files = await generate_json(
                self.skill_prompt(instruction),
                json.dumps({"contract": contract, "plan": plan, "verification_gaps": gaps},
                           ensure_ascii=False),
                capability="coding",
                validator=lambda payload: validate_code_files(payload, project_type),
            )
            paths = write_code_files(contract["project_name"], files, project_type)
            return {"files": paths, "message": "Browser prototype source written"}

        files = await generate_json(
            self.skill_prompt("Return only a JSON object with keys main.py and test_main.py, each a full Python source string. "
            "Make a simple CLI whose --help command exits successfully without waiting for input. "
            "Use argparse to parse input. The Test Writer will replace test_main.py, so its "
            "content here only needs to be a valid initial test. Implement every approved "
            "acceptance criterion. If verification gaps are supplied, repair those gaps "
            "without dropping already implemented behavior. "
            "Use standard library only in main.py. No markdown fences or extra keys."),
            json.dumps({"contract": contract, "plan": plan, "verification_gaps": gaps},
                       ensure_ascii=False),
            capability="coding",
            validator=validate_code_files,
        )
        paths = write_code_files(contract["project_name"], files, project_type)
        return {"files": paths, "message": "Code and tests written"}

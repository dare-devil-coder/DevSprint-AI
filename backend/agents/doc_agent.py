# Generate a project README from the approved plan and verified output.
"""Generate a project README from the approved plan and verified output."""

from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.agents.coder_agent import source_files_for_type
from backend.memory.shared_memory import (
    CONTRACT_FILE, PLAN_FILE, VERIFICATION_FILE, WORKSPACE_DIR, read_json,
)


class DocAgent(BaseAgent):
    """Write installation, usage, tests, features, and limits for the project."""

    def __init__(self) -> None:
        """Name the documentation agent."""
        super().__init__("Doc Agent", "doc")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Assemble a factual README from saved contract and verification data."""
        contract = context["memory"]["contract"] if "memory" in context else read_json(CONTRACT_FILE)
        plan = context["memory"]["plan"] if "memory" in context else read_json(PLAN_FILE)
        report = context["memory"]["verification"] if "memory" in context else read_json(VERIFICATION_FILE)
        project = WORKSPACE_DIR / contract["project_name"]
        project_type = contract.get("project_type", "python_cli")
        required = source_files_for_type(project_type) + ["test_main.py"]
        if not all((project / name).is_file() for name in required):
            raise FileNotFoundError("Generated source and tests are required for documentation.")
        tests_source = (project / "test_main.py").read_text(encoding="utf-8")
        features = "\n".join(f"- {item['feature']}" for item in plan["acceptance_criteria"])
        limitations = [str(item) for item in plan.get("risks", []) if str(item).strip()]
        limitations.extend(f"{gap['feature']}: {gap['reason']}" for gap in report.get("gaps", []))
        if "# Deterministic fallback: source-level smoke checks" in tests_source:
            limitations.append(
                "Model providers were unavailable during test generation. The generated tests "
                "check source-level signals and do not exercise browser interactions."
            )
        if project_type == "web_app":
            limitations.append("This is a local browser prototype without production authentication, server-side storage, or hosted APIs.")
            run_instructions = (
                "Use Python 3.10 or newer. From this directory, run `python -m http.server 8000`, "
                "then open http://localhost:8000 in a browser. The prototype uses vanilla HTML, CSS, "
                "and JavaScript and has no external runtime dependencies.\n\n"
            )
        else:
            run_instructions = (
                "Use Python 3.10 or newer. Install pytest to run the tests with "
                "`python -m pip install pytest`.\n\n"
                "Run `python main.py --help` for supported arguments, or `python main.py` "
                "to start with its default behavior.\n\n"
            )
        if not limitations:
            limitations = ["No known limitations were identified by the plan or verification report."]
        content = (
            f"# {contract['app_name']}\n\n"
            f"{contract['description']}\n\n"
            "## Project type\n\n"
            f"{'Browser prototype' if project_type == 'web_app' else 'Python command-line tool'}\n\n"
            "## How to run\n\n"
            f"{run_instructions}"
            "## How to run tests\n\n"
            "Run `python -m pytest -q test_main.py`.\n\n"
            "## Files\n\n"
            + "\n".join(f"- `{name}`" for name in required) + "\n\n"
            "## Features\n\n"
            f"{features}\n\n"
            "## Known limitations\n\n"
            + "\n".join(f"- {item}" for item in limitations) + "\n"
        )
        target = project / "README.md"
        target.write_text(content, encoding="utf-8")
        return {"files": [f"{contract['project_name']}/README.md"],
                "message": "Project README written"}

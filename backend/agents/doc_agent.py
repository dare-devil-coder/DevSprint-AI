# Generate a project README from the approved plan and verified output.
"""Generate a project README from the approved plan and verified output."""

from typing import Any

from backend.agents.base_agent import BaseAgent
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
        contract = read_json(CONTRACT_FILE)
        plan = read_json(PLAN_FILE)
        report = read_json(VERIFICATION_FILE)
        project = WORKSPACE_DIR / contract["project_name"]
        if not (project / "main.py").is_file() or not (project / "test_main.py").is_file():
            raise FileNotFoundError("Generated source and tests are required for documentation.")
        features = "\n".join(f"- {item['feature']}" for item in plan["acceptance_criteria"])
        limitations = [str(item) for item in plan.get("risks", []) if str(item).strip()]
        limitations.extend(f"{gap['feature']}: {gap['reason']}" for gap in report.get("gaps", []))
        if not limitations:
            limitations = ["No known limitations were identified by the plan or verification report."]
        content = (
            f"# {contract['app_name']}\n\n"
            "## What it does\n\n"
            f"{contract['description']}\n\n"
            "## How to install\n\n"
            "Use Python 3.10 or newer. Install pytest to run the tests: "
            "python -m pip install pytest.\n\n"
            "## How to run\n\n"
            "Run python main.py --help for supported arguments, or python main.py "
            "to start with its default behavior.\n\n"
            "## How to run tests\n\n"
            "Run python -m pytest -q test_main.py.\n\n"
            "## Features\n\n"
            f"{features}\n\n"
            "## Known limitations\n\n"
            + "\n".join(f"- {item}" for item in limitations) + "\n"
        )
        target = project / "README.md"
        target.write_text(content, encoding="utf-8")
        return {"files": [f"{contract['project_name']}/README.md"],
                "message": "Project README written"}

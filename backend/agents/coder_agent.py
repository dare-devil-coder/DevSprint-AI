# Generate the main program and its tests from the project contract.
"""Generate the main program and its tests from the project contract."""

import json
from pathlib import Path
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, PLAN_FILE, WORKSPACE_DIR, read_json


def write_code_files(project_name: str, files: dict[str, Any]) -> list[str]:
    """Validate and write exactly the two allowed generated Python files."""
    if not all(isinstance(files.get(name), str) and files[name].strip()
               for name in ("main.py", "test_main.py")):
        raise ValueError("The model must return nonempty main.py and test_main.py strings.")
    root = WORKSPACE_DIR / project_name
    root.mkdir(parents=True, exist_ok=True)
    for name in ("main.py", "test_main.py"):
        (root / name).write_text(files[name], encoding="utf-8")
    return [f"{project_name}/main.py", f"{project_name}/test_main.py"]


class CoderAgent(BaseAgent):
    """Build a small standalone Python CLI implementation."""

    def __init__(self) -> None:
        """Name the coding agent."""
        super().__init__("Coder", "coder")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist code from the saved contract."""
        contract = read_json(CONTRACT_FILE)
        plan = read_json(PLAN_FILE)
        gaps = context.get("gaps", [])
        files = await generate_json(
            "Return only a JSON object with keys main.py and test_main.py, each a full Python source string. "
            "Make a simple CLI that runs and exits without waiting for input when invoked with no arguments. "
            "Use argparse for optional input. The Test Writer will replace test_main.py, so its "
            "content here only needs to be a valid initial test. Implement every approved "
            "acceptance criterion. If verification gaps are supplied, repair those gaps "
            "without dropping already implemented behavior. "
            "Use standard library only in main.py. No markdown fences or extra keys.",
            json.dumps({"contract": contract, "plan": plan, "verification_gaps": gaps},
                       ensure_ascii=False),
        )
        paths = write_code_files(contract["project_name"], files)
        return {"files": paths, "message": "Code and tests written"}

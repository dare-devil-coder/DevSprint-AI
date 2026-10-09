# Build and validate the Python project plan before approval.
"""Build and validate the Python project plan before approval."""

import json
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, PLAN_FILE, read_json, write_json


class ArchitectureAgent(BaseAgent):
    """Turn the contract into a bounded plan for two Python source files."""

    def __init__(self) -> None:
        """Name the planning agent."""
        super().__init__("Architecture", "architecture")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate a plan and reject unsafe or incomplete file structures."""
        contract = read_json(CONTRACT_FILE)
        data = await generate_json(
            "Return only JSON with project_name, tech_stack, file_structure, build_order, "
            "acceptance_criteria, risks. This is a small Python CLI. tech_stack has language "
            "'python' and a libraries string array. file_structure has exactly main.py and "
            "test_main.py entries, each with path, purpose, depends_on string array. "
            "build_order is ['main.py','test_main.py']. Each acceptance criterion has "
            "feature, given, when, then strings, based only on the contract. risks is a "
            "string array. Do not invent UI, API, or database layers.",
            json.dumps(contract, ensure_ascii=False),
        )
        stack = data.get("tech_stack")
        structure = data.get("file_structure")
        criteria = data.get("acceptance_criteria")
        if not isinstance(stack, dict) or str(stack.get("language", "")).lower() != "python":
            raise ValueError("The architecture plan must use Python.")
        if not isinstance(stack.get("libraries"), list) or not all(
            isinstance(item, str) for item in stack["libraries"]
        ):
            raise ValueError("The architecture libraries must be strings.")
        if not isinstance(structure, list) or {item.get("path") for item in structure
                                               if isinstance(item, dict)} != {"main.py", "test_main.py"}:
            raise ValueError("The architecture must describe main.py and test_main.py only.")
        if any(not isinstance(item.get("purpose"), str)
               or not isinstance(item.get("depends_on"), list)
               or any(dependency not in {"main.py", "test_main.py"}
                      for dependency in item["depends_on"]) for item in structure):
            raise ValueError("The architecture file descriptions are incomplete.")
        if data.get("build_order") != ["main.py", "test_main.py"]:
            raise ValueError("The architecture build order is invalid.")
        if not isinstance(criteria, list) or not criteria or any(
            not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip()
                                                 for key in ("feature", "given", "when", "then"))
            for item in criteria
        ):
            raise ValueError("The architecture needs complete acceptance criteria.")
        if not isinstance(data.get("risks"), list) or not all(
            isinstance(item, str) for item in data["risks"]
        ):
            raise ValueError("The architecture risks must be strings.")
        plan = {
            "project_name": contract["project_name"],
            "tech_stack": {"language": "python", "libraries": stack["libraries"]},
            "file_structure": structure,
            "build_order": data["build_order"],
            "acceptance_criteria": criteria,
            "risks": data["risks"],
        }
        write_json(PLAN_FILE, plan)
        return {"plan": plan, "message": "Architecture plan ready"}

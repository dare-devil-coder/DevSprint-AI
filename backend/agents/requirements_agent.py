# Collect four answers and turn them into a validated project contract.
"""Collect four answers and turn them into a validated project contract."""

import json
import re
from dataclasses import asdict
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, write_json
from backend.models.contract import ProjectContract

QUESTIONS = [
    "Describe what you want to build in your own words.",
    "What should the tool take as input?",
    "What should the tool output?",
    "Any edge cases to handle (empty input, invalid input)?",
]


class RequirementsAgent(BaseAgent):
    """Generate a concise contract after the chat has gathered all answers."""

    def __init__(self) -> None:
        """Name the clarification agent."""
        super().__init__("Requirements", "requirements")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Ask OpenAI for a contract and validate every required field."""
        payload = {"idea": context["idea"], "answers": context["answers"]}
        data = await generate_json(
            "Produce only a JSON object with app_name, description, inputs, outputs, edge_cases. "
            "The last three fields must be arrays of plain strings. Build a small Python CLI program. "
            "Use a short descriptive app_name. Preserve the user's actual requirements; invent no features.",
            json.dumps(payload, ensure_ascii=False),
        )
        name = str(data.get("app_name", "")).strip()
        description = str(data.get("description", "")).strip()
        if not name or not description:
            raise ValueError("The generated contract needs an app name and description.")
        arrays: dict[str, list[str]] = {}
        for field in ("inputs", "outputs", "edge_cases"):
            value = data.get(field)
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"The contract field {field} must be a list of strings.")
            arrays[field] = [item.strip() for item in value if item.strip()]
        contract = ProjectContract(name, description, **arrays)
        contract_data = asdict(contract)
        contract_data["project_name"] = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "project"
        write_json(CONTRACT_FILE, contract_data)
        return {"contract": contract_data, "message": "Project contract ready"}

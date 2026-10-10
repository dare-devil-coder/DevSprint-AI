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
    "Which format should I build: a browser-based web app or a Python command-line tool?",
    "What should the tool take as input?",
    "What should the tool output?",
    "Any edge cases to handle (empty input, invalid input)?",
]

WEB_QUESTIONS = [
    "What are the main screens and actions? Describe the path from opening the app to getting a result.",
    "Who will use it, and what visual style or reference should guide the interface?",
    "What should it display or remember, and how should empty, invalid, or loading states behave?",
]

CLI_QUESTIONS = [
    "What commands or options should users run, and what should each command do?",
    "Who will use it, and what input and output format should the commands use?",
    "Which invalid inputs, boundaries, or error cases should it handle?",
]


def infer_project_type(idea: str, answers: list[str] | None = None) -> str:
    """Choose the requested delivery format, honoring the explicit format answer first."""
    explicit = (answers or [""])[0].casefold()
    if any(term in explicit for term in ("web app", "web application", "website", "browser")):
        return "web_app"
    if any(term in explicit for term in ("cli", "command line", "command-line", "terminal")):
        return "python_cli"
    text = (idea + " " + " ".join(answers or [])).casefold()
    cli_terms = (" cli", "command line", "command-line", "terminal tool", "python script")
    return "python_cli" if any(term in text for term in cli_terms) else "web_app"


def questions_for_project(idea: str, answers: list[str] | None = None) -> list[str]:
    """Ask platform-specific follow-ups while keeping the user's idea as context."""
    followups = CLI_QUESTIONS if infer_project_type(idea, answers) == "python_cli" else WEB_QUESTIONS
    return [QUESTIONS[0], *followups]


class RequirementsAgent(BaseAgent):
    """Generate a concise contract after the chat has gathered all answers."""

    def __init__(self) -> None:
        """Name the clarification agent."""
        super().__init__("Requirements", "requirements")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Ask OpenAI for a contract and validate every required field."""
        payload = {"idea": context["idea"], "answers": context["answers"]}
        data = await generate_json(
            self.skill_prompt("Produce only JSON with app_name, description, inputs, outputs, edge_cases, "
            "project_type, and design_direction. project_type must be 'web_app' or 'python_cli'. "
            "Choose it from the original idea and the user's first format answer; an explicit answer wins. "
            "Use web_app for browser interfaces, sites, dashboards, and interactive prototypes; use "
            "python_cli only when the user asks for a CLI, terminal tool, or Python script. "
            "Preserve the requested screens, actions, audience, style, data, and constraints in description "
            "and the arrays. The inputs, outputs, and edge_cases fields must be arrays of plain strings. "
            "Use a short descriptive app_name. Add no features the user did not request."),
            json.dumps(payload, ensure_ascii=False),
            capability="requirements",
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
        requested_type = data.get("project_type")
        project_type = infer_project_type(context["idea"], context["answers"])
        if requested_type not in {"web_app", "python_cli"}:
            requested_type = project_type
        # The user's explicit format answer takes precedence over a model classification.
        project_type = project_type if context["answers"] else requested_type
        direction = data.get("design_direction") or (
            context["answers"][2] if len(context["answers"]) > 2 else "")
        if not isinstance(direction, str):
            raise ValueError("The contract field design_direction must be a string.")
        contract = ProjectContract(name, description, **arrays,
                                   project_type=project_type,
                                   design_direction=direction.strip())
        contract_data = asdict(contract)
        contract_data["project_name"] = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "project"
        write_json(CONTRACT_FILE, contract_data)
        return {"contract": contract_data, "message": "Project contract ready"}

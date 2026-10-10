# Build and validate the Python project plan before approval.
"""Build and validate the Python project plan before approval."""

import json
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, PLAN_FILE, read_json, write_json


def validate_architecture(data: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Normalize a complete CLI or browser-app plan and reject unsafe file lists."""
    project_type = contract.get("project_type", "python_cli")
    if project_type not in {"web_app", "python_cli"}:
        raise ValueError("The contract must choose web_app or python_cli.")
    if data.get("project_type", project_type) != project_type:
        raise ValueError("The architecture project_type must match the approved contract.")
    required = ( ["index.html", "styles.css", "app.js", "test_main.py"]
                 if project_type == "web_app" else ["main.py", "test_main.py"] )
    language = "html_css_javascript" if project_type == "web_app" else "python"
    stack = data.get("tech_stack")
    structure = data.get("file_structure")
    criteria = data.get("acceptance_criteria")
    if not isinstance(stack, dict) or str(stack.get("language", "")).lower() != language:
        raise ValueError(f"The architecture plan must use {language} for {project_type}.")
    if not isinstance(stack.get("libraries"), list) or not all(
        isinstance(item, str) for item in stack["libraries"]
    ):
        raise ValueError("The architecture libraries must be strings.")
    if not isinstance(structure, list) or [item.get("path") for item in structure
                                           if isinstance(item, dict)] != required:
        if project_type == "python_cli":
            raise ValueError("The architecture must describe main.py and test_main.py only.")
        raise ValueError("The architecture file list does not match the selected project type.")
    if any(not isinstance(item.get("purpose"), str)
           or not isinstance(item.get("depends_on"), list)
           or any(dependency not in set(required)
                  for dependency in item["depends_on"]) for item in structure):
        raise ValueError("The architecture file descriptions are incomplete.")
    if data.get("build_order") != required:
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
    return {
        "project_name": contract["project_name"],
        "project_type": project_type,
        "tech_stack": {"language": language, "libraries": stack["libraries"]},
        "file_structure": structure,
        "build_order": data["build_order"],
        "acceptance_criteria": criteria,
        "risks": data["risks"],
    }


class ArchitectureAgent(BaseAgent):
    """Turn the user's contract into a type-specific, bounded prototype plan."""

    def __init__(self) -> None:
        """Name the planning agent."""
        super().__init__("Architecture", "architecture")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate a plan and reject unsafe or incomplete file structures."""
        contract = context["memory"]["contract"] if "memory" in context else read_json(CONTRACT_FILE)

        def check_plan(candidate: dict[str, Any]) -> None:
            """Ask the LLM router to reject incomplete architecture candidates."""
            validate_architecture(candidate, contract)

        project_type = contract.get("project_type", "python_cli")
        file_list = ("index.html, styles.css, app.js, test_main.py" if project_type == "web_app"
                     else "main.py, test_main.py")
        order = (["index.html", "styles.css", "app.js", "test_main.py"]
                 if project_type == "web_app" else ["main.py", "test_main.py"])
        language = "html_css_javascript" if project_type == "web_app" else "python"
        data = await generate_json(
            self.skill_prompt("Return only JSON with project_name, project_type, tech_stack, file_structure, "
            "build_order, acceptance_criteria, risks. Respect contract.project_type exactly. "
            f"For {project_type}, tech_stack.language is '{language}' and libraries is a string array. "
            f"file_structure must contain exactly these files in this order: {file_list}. "
            "Each file has path, purpose, and depends_on string array. "
            f"build_order is {json.dumps(order)}. For web_app, plan a polished, responsive, "
            "accessible browser prototype with working interactions using only vanilla HTML, CSS, "
            "and JavaScript; use in-memory sample state and do not claim production authentication, "
            "cloud storage, or APIs. For python_cli, plan a usable command-line tool. "
            "Acceptance criteria must directly reflect the user's idea and answers; include the "
            "requested primary workflow and visual direction. Each criterion has feature, given, "
            "when, then strings. risks is a string array. Do not add unrequested product features."),
            json.dumps(contract, ensure_ascii=False),
            capability="architecture",
            validator=check_plan,
        )
        plan = validate_architecture(data, contract)
        write_json(PLAN_FILE, plan)
        return {"plan": plan, "message": "Architecture plan ready"}

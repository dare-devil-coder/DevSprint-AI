# Write pytest acceptance tests from the approved plan and generated source.
"""Write pytest acceptance tests from the approved plan and generated source."""

import ast
import json
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, PLAN_FILE, WORKSPACE_DIR, read_json


class TestWriterAgent(BaseAgent):
    """Generate tests that trace back to each acceptance criterion."""

    def __init__(self) -> None:
        """Name the testing agent."""
        super().__init__("Test Writer", "test_writer")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Write a valid pytest file with a named check for every feature."""
        contract = read_json(CONTRACT_FILE)
        plan = read_json(PLAN_FILE)
        project = WORKSPACE_DIR / contract["project_name"]
        source = (project / "main.py").read_text(encoding="utf-8")
        criteria = plan["acceptance_criteria"]
        data = await generate_json(
            "Return only a JSON object with test_main.py as the full pytest source string. "
            "For every acceptance criterion, include a test function and a comment exactly "
            "'# Acceptance: <feature>' immediately above that test, using the feature text "
            "verbatim. Test observable behavior, including edge cases. Do not mock the code "
            "under test or weaken assertions to make failures pass. No extra files.",
            json.dumps({"contract": contract, "plan": plan, "main.py": source}, ensure_ascii=False),
        )
        tests = data.get("test_main.py")
        if not isinstance(tests, str) or not tests.strip():
            raise ValueError("The Test Writer must produce test_main.py.")
        try:
            parsed = ast.parse(tests)
        except SyntaxError as exc:
            raise ValueError(f"The generated test file has invalid syntax: {exc}") from exc
        lines = tests.splitlines()
        test_functions = [node for node in parsed.body
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and node.name.startswith("test_")]
        mapped = {lines[node.lineno - 2].strip() for node in test_functions
                  if node.lineno >= 2}
        test_count = len(test_functions)
        if test_count < len(criteria) or any(
            f"# Acceptance: {item['feature']}" not in mapped for item in criteria
        ):
            raise ValueError("Each acceptance criterion needs a mapped pytest test.")
        project.mkdir(parents=True, exist_ok=True)
        (project / "test_main.py").write_text(tests, encoding="utf-8")
        return {"files": [f"{contract['project_name']}/test_main.py"],
                "test_count": test_count, "message": f"{test_count} acceptance tests written"}

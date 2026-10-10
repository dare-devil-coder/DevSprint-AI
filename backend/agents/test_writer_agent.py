# Write pytest acceptance tests from the approved plan and generated source.
"""Write pytest acceptance tests from the approved plan and generated source."""

import ast
import json
import re
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.agents.coder_agent import source_files_for_type
from backend.llm_client import generate_json
from backend.memory.shared_memory import CONTRACT_FILE, PLAN_FILE, WORKSPACE_DIR, read_json

GENERIC_WORDS = {
    "test", "operation", "handling", "input", "case", "valid", "with", "the",
    "user", "they", "their", "when", "then", "given", "from", "into", "only",
    "this", "that", "same", "before", "after", "one", "more", "all", "any",
    "app", "task", "tasks", "data", "state", "current", "appears", "updates",
    "updated", "displayed", "shown", "shows", "change", "changes", "list", "form",
}


def build_source_smoke_tests(criteria: list[dict[str, Any]],
                             source: dict[str, str]) -> str:
    """Build honest source-based acceptance smoke checks when all model providers fail."""
    if not criteria or not source:
        raise ValueError("Cannot build fallback tests without source files and acceptance criteria.")
    lines = [
        "# Deterministic fallback: source-level smoke checks, not browser behavior tests.",
        "from pathlib import Path",
        "ROOT = Path(__file__).parent",
        "SOURCE = {name: (ROOT / name).read_text(encoding='utf-8') for name in "
        f"{sorted(source)!r}" + "}",
        "COMBINED = '\\n'.join(SOURCE.values()).casefold()",
        "",
        "def test_generated_sources_exist_and_are_nonempty():",
        "    assert SOURCE and all(content.strip() for content in SOURCE.values())",
    ]
    for index, criterion in enumerate(criteria, start=1):
        feature = criterion["feature"]
        description = " ".join(str(criterion.get(field, "")) for field in
                               ("feature", "given", "when", "then"))
        tokens = _feature_words(description)
        aliases = {
            "inline": {"error", "errors", "invalid", "message", "messages"},
            "validation": {"validate", "validated", "required", "invalid", "error"},
            "persistence": {"localstorage", "storage", "persist", "save", "saved"},
            "persisted": {"localstorage", "storage", "persistence", "save"},
            "restores": {"restore", "restored", "localstorage", "storage"},
        }
        tokens.update(*(aliases.get(word, set()) for word in tuple(tokens)))
        tokens = sorted(tokens)
        if not tokens:
            raise ValueError(f"Cannot derive a source smoke check for acceptance criterion: {feature}.")
        quoted = repr(tokens)
        lines.extend([
            "",
            f"# Acceptance: {feature}",
            f"def test_acceptance_source_signal_{index}():",
            f"    terms = {quoted}",
            "    assert any(term in COMBINED for term in terms), "
            f"{('No source text matched acceptance criterion: ' + feature)!r}",
        ])
    return "\n".join(lines) + "\n"


def _feature_words(value: str) -> set[str]:
    """Extract meaningful words for matching a criterion to a test name."""
    return set(re.findall(r"[a-z0-9]+", value.casefold().replace("‑", "-"))) - GENERIC_WORDS


def add_missing_acceptance_labels(data: dict[str, Any],
                                  criteria: list[dict[str, Any]]) -> None:
    """Label clearly named tests when a model omitted required mapping comments."""
    source = data.get("test_main.py")
    if not isinstance(source, str):
        return
    try:
        parsed = ast.parse(source)
    except SyntaxError:
        return
    functions = [node for node in parsed.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.name.startswith("test_")]
    if len(functions) < len(criteria):
        return
    lines = source.splitlines()
    assignments: dict[int, str] = {}
    remaining = list(functions)
    for criterion in sorted(criteria, key=lambda item: -len(_feature_words(item["feature"]))):
        words = _feature_words(criterion["feature"])
        ranked = sorted(
            ((len(words & _feature_words(node.name)), node) for node in remaining),
            key=lambda pair: pair[0], reverse=True,
        )
        if not words or not ranked or ranked[0][0] == 0 or ranked[0][0] / len(words) < 0.5:
            return
        node = ranked[0][1]
        remaining.remove(node)
        anchor = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
        assignments[anchor - 1] = f"# Acceptance: {criterion['feature']}"
    for index, label in sorted(assignments.items(), reverse=True):
        lines.insert(index, label)
    data["test_main.py"] = "\n".join(lines) + "\n"


def validate_generated_tests(data: dict[str, Any],
                             criteria: list[dict[str, Any]]) -> tuple[str, int]:
    """Require parseable pytest source and one labeled function per criterion."""
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
    if any(isinstance(node, ast.Assert) and isinstance(node.test, ast.Constant)
           and node.test.value is True for function in test_functions
           for node in ast.walk(function)):
        raise ValueError("Generated tests contain a placeholder 'assert True' check.")
    mapped: set[str] = set()
    for node in test_functions:
        anchors = [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
        for anchor in anchors:
            cursor = anchor - 2
            while cursor >= 0 and not lines[cursor].strip():
                cursor -= 1
            if cursor >= 0 and lines[cursor].strip().startswith("# Acceptance: "):
                mapped.add(lines[cursor].strip())
                break
    test_count = len(test_functions)
    if test_count < len(criteria) or any(
        f"# Acceptance: {item['feature']}" not in mapped for item in criteria
    ):
        raise ValueError("Each acceptance criterion needs a mapped pytest test.")
    return tests, test_count


class TestWriterAgent(BaseAgent):
    """Generate tests that trace back to each acceptance criterion."""

    def __init__(self) -> None:
        """Name the testing agent."""
        super().__init__("Test Writer", "test_writer")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Write a valid pytest file with a named check for every feature."""
        contract = context["memory"]["contract"] if "memory" in context else read_json(CONTRACT_FILE)
        plan = context["memory"]["plan"] if "memory" in context else read_json(PLAN_FILE)
        project = WORKSPACE_DIR / contract["project_name"]
        source_names = [name for name in source_files_for_type(
            contract.get("project_type", "python_cli")) if name != "test_main.py"]
        memory_files = context.get("memory", {}).get("files", {})
        source = ({name: memory_files[name] for name in source_names if name in memory_files}
                  if memory_files else {name: (project / name).read_text(encoding="utf-8")
                                        for name in source_names})
        criteria = plan["acceptance_criteria"]

        def check_tests(payload: dict[str, Any]) -> None:
            """Reject unsuitable model output so the LLM router tries another provider."""
            add_missing_acceptance_labels(payload, criteria)
            validate_generated_tests(payload, criteria)

        try:
            data = await generate_json(
                self.skill_prompt("Return only a JSON object with test_main.py as the full pytest source string. "
                "For every acceptance criterion, include a test function and a comment exactly "
                "'# Acceptance: <feature>' immediately above that test, using the feature text "
                "verbatim. Test observable behavior, including edge cases. Do not mock the code "
                "under test or weaken assertions to make failures pass. Keep tests concise. "
                "Do not assert exact ASCII-art spacing or error wording unless the approved "
                "criterion specifies it. For web_app projects, test the generated HTML, CSS, and "
                "JavaScript by reading the approved source files from Path(__file__).parent; assert "
                "the requested screens, labels, interactions, and states are present in those files. "
                "Use only Python's standard library and pytest."),
                json.dumps({"contract": contract, "plan": plan, "source_files": source}, ensure_ascii=False),
                capability="testing",
                validator=check_tests,
            )
            message = "Acceptance tests written"
        except RuntimeError as error:
            if "No JSON-capable model is available for testing" not in str(error):
                raise
            fallback = build_source_smoke_tests(criteria, source)
            data = {"test_main.py": fallback}
            check_tests(data)
            message = "Provider tests unavailable; deterministic source smoke checks written"
        tests, test_count = validate_generated_tests(data, criteria)
        project.mkdir(parents=True, exist_ok=True)
        (project / "test_main.py").write_text(tests, encoding="utf-8")
        return {"files": [f"{contract['project_name']}/test_main.py"],
                "test_count": test_count, "message": f"{test_count} acceptance checks written. {message}."}

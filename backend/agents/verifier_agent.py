# Verify generated code against observed execution and approved criteria.
"""Verify generated code against observed execution and approved criteria."""

import ast
import json
import re
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import (
    CONTRACT_FILE, OUTPUT_FILE, PLAN_FILE, VERIFICATION_FILE, WORKSPACE_DIR,
    read_json, write_json,
)

LAYER_NAMES = ("frontend", "backend", "database", "apis", "config", "build")
VALID_STATUSES = {"pass", "fail", "partial"}
GENERIC_FEATURE_WORDS = {
    "a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is",
    "it", "of", "on", "or", "the", "to", "user", "when", "then", "given",
}


def mapped_assertion(source: str, feature: str) -> str | None:
    """Find an exact assertion in a pytest function labeled for one criterion."""
    try:
        parsed = ast.parse(source)
    except SyntaxError:
        return None
    lines = source.splitlines()
    label = f"# Acceptance: {feature}"
    feature_words = set(re.findall(r"[a-z0-9]+", feature.casefold())) - GENERIC_FEATURE_WORDS
    for node in parsed.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        anchors = [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
        def has_label(anchor: int) -> bool:
            """Allow blank lines between a mapping comment and its decorator or test."""
            cursor = anchor - 2
            while cursor >= 0 and not lines[cursor].strip():
                cursor -= 1
            return cursor >= 0 and lines[cursor].strip() == label

        if not any(has_label(anchor) for anchor in anchors):
            continue
        semantic_tokens = {
            child.id.casefold() for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        semantic_tokens.update(
            child.value.casefold() for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        )
        if feature_words and not any(
            word in token for word in feature_words for token in semantic_tokens
        ):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                excerpt = ast.get_source_segment(source, child)
                if excerpt:
                    return excerpt
    return None


class VerifierAgent(BaseAgent):
    """Assess feature coverage while keeping observed test results authoritative."""

    def __init__(self) -> None:
        """Name the verification agent."""
        super().__init__("Verifier", "verifier")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Write a grounded per-layer and per-feature verification report."""
        contract = context["memory"]["contract"] if "memory" in context else read_json(CONTRACT_FILE)
        plan = context["memory"]["plan"] if "memory" in context else read_json(PLAN_FILE)
        output = context["memory"]["output"] if "memory" in context else read_json(OUTPUT_FILE)
        project = WORKSPACE_DIR / contract["project_name"]
        planned_files = [item["path"] for item in plan.get("file_structure", [])
                         if isinstance(item, dict) and item.get("path") != "README.md"]
        code = (context["memory"]["files"] if "memory" in context else
                {name: (project / name).read_text(encoding="utf-8")
                 for name in planned_files if (project / name).is_file()})
        combined = "\n".join(code.values())
        project_type = contract.get("project_type", "python_cli")
        project_guidance = ("This is a browser prototype. Assess the requested UI workflows, accessibility, "
                            "responsive behavior, and visible states against the supplied HTML/CSS/JS and tests."
                            if project_type == "web_app" else
                            "This is a Python CLI. Assess its requested commands and outputs against source and tests.")
        verifier_prompt = self.skill_prompt(
            "Return only JSON with a features array. Give exactly one item per acceptance "
            "criterion, with feature matching its name verbatim, status pass|fail|partial, "
            "and evidence as an exact short source-code or test-code excerpt copied from "
            "the supplied files. Use pass only when the code and test demonstrate the "
            "criterion; use partial if evidence is incomplete. Do not invent evidence. "
            + project_guidance
        )
        verifier_input = json.dumps({"contract": contract, "plan": plan, "code": code,
                                     "execution": output}, ensure_ascii=False)
        try:
            result = await generate_json(
                verifier_prompt, verifier_input, capability="verification",
            )
        except RuntimeError as error:
            # Provider outages must not strand a successfully executed project before docs.
            # The local fallback only passes a criterion when pytest passed and the mapped
            # acceptance test contains an actual assertion; otherwise it records a gap.
            if "No JSON-capable model is available for verification" not in str(error):
                raise
            tests = code.get("test_main.py", "")
            result = {"features": [
                {
                    "feature": item["feature"],
                    "status": "pass" if output.get("success") and
                    mapped_assertion(tests, item["feature"]) else "partial",
                    "evidence": mapped_assertion(tests, item["feature"]) or
                    "No passing, criterion-mapped assertion is available.",
                }
                for item in plan["acceptance_criteria"]
            ]}
        proposed = result.get("features")
        if not isinstance(proposed, list):
            raise ValueError("The Verifier must return a features array.")
        by_feature = {item.get("feature"): item for item in proposed if isinstance(item, dict)}
        features: list[dict[str, str]] = []
        gaps: list[dict[str, str]] = []
        for criterion in plan["acceptance_criteria"]:
            name = criterion["feature"]
            item = by_feature.get(name, {})
            status = item.get("status", "fail")
            evidence = item.get("evidence", "")
            if status not in VALID_STATUSES or not isinstance(evidence, str):
                status, evidence = "fail", "The verifier returned an invalid result."
            elif status == "pass" and (not output.get("success") or not evidence.strip()
                                        or evidence not in combined):
                assertion = (mapped_assertion(code.get("test_main.py", ""), name)
                             if output.get("success") else None)
                if assertion:
                    evidence = assertion
                else:
                    status = "partial"
                    evidence = "Passing execution or exact source evidence is missing."
            if not evidence:
                evidence = "No evidence was provided."
            features.append({"feature": name, "status": status, "evidence": evidence})
            if status != "pass":
                gaps.append({"feature": name, "reason": evidence})
        built = bool(planned_files) and all((project / name).is_file() for name in planned_files)
        execution_passed = bool(output.get("success"))
        if project_type == "web_app":
            layers = [
                {"name": "frontend", "status": "pass" if built and execution_passed else "fail",
                 "details": "The approved browser assets and prototype checks passed." if built and execution_passed
                 else "One or more browser assets are missing or failed checks."},
                {"name": "backend", "status": "na", "details": "The requested deliverable is a local browser prototype."},
                {"name": "database", "status": "na", "details": "No persistent database was requested or planned."},
                {"name": "apis", "status": "na", "details": "No hosted API is included in this local prototype."},
                {"name": "config", "status": "na", "details": "No external runtime configuration is required."},
                {"name": "build", "status": "pass" if execution_passed else "fail",
                 "details": "Prototype checks and acceptance tests passed." if execution_passed else "A prototype check or acceptance test failed."},
            ]
        else:
            layers = [
                {"name": "frontend", "status": "na", "details": "This project is a Python CLI."},
                {"name": "backend", "status": "pass" if built and execution_passed else "fail",
                 "details": "Both Python source files exist and the program ran." if built and execution_passed
                 else "Source files or successful execution are missing."},
                {"name": "database", "status": "na", "details": "The approved plan has no database."},
                {"name": "apis", "status": "na", "details": "The approved plan has no API."},
                {"name": "config", "status": "na", "details": "No configuration layer is in the approved plan."},
                {"name": "build", "status": "pass" if execution_passed else "fail",
                 "details": "Program and pytest passed." if execution_passed else "Execution or pytest failed."},
            ]
        statuses = [item["status"] for item in layers + features]
        summary = {key: statuses.count(key) for key in ("pass", "partial", "fail", "na")}
        report = {"layers": layers, "features": features, "summary": {
            "passed": summary["pass"], "partial": summary["partial"],
            "failed": summary["fail"], "na": summary["na"],
        }, "gaps": gaps}
        write_json(VERIFICATION_FILE, report)
        return {"gaps": gaps, "report": report,
                "message": "Verification passed" if not gaps else f"{len(gaps)} gap(s) found"}

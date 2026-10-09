# Verify generated code against observed execution and approved criteria.
"""Verify generated code against observed execution and approved criteria."""

import json
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.llm_client import generate_json
from backend.memory.shared_memory import (
    CONTRACT_FILE, OUTPUT_FILE, PLAN_FILE, VERIFICATION_FILE, WORKSPACE_DIR,
    read_json, write_json,
)

LAYER_NAMES = ("frontend", "backend", "database", "apis", "config", "build")
VALID_STATUSES = {"pass", "fail", "partial"}


class VerifierAgent(BaseAgent):
    """Assess feature coverage while keeping observed test results authoritative."""

    def __init__(self) -> None:
        """Name the verification agent."""
        super().__init__("Verifier", "verifier")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Write a grounded per-layer and per-feature verification report."""
        contract = read_json(CONTRACT_FILE)
        plan = read_json(PLAN_FILE)
        output = read_json(OUTPUT_FILE)
        project = WORKSPACE_DIR / contract["project_name"]
        code = {name: (project / name).read_text(encoding="utf-8")
                for name in ("main.py", "test_main.py")}
        combined = "\n".join(code.values())
        result = await generate_json(
            "Return only JSON with a features array. Give exactly one item per acceptance "
            "criterion, with feature matching its name verbatim, status pass|fail|partial, "
            "and evidence as an exact short source-code or test-code excerpt copied from "
            "the supplied files. Use pass only when the code and test demonstrate the "
            "criterion; use partial if evidence is incomplete. Do not invent evidence. "
            "Do not assess frontend, APIs, or database for this Python CLI.",
            json.dumps({"contract": contract, "plan": plan, "code": code,
                        "execution": output}, ensure_ascii=False),
        )
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
                status = "partial"
                evidence = "Passing execution or exact source evidence is missing."
            if not evidence:
                evidence = "No evidence was provided."
            features.append({"feature": name, "status": status, "evidence": evidence})
            if status != "pass":
                gaps.append({"feature": name, "reason": evidence})
        built = all((project / name).is_file() for name in ("main.py", "test_main.py"))
        execution_passed = bool(output.get("success"))
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

# Supply small, tagged context slices to each project agent.
"""Scoped JSON memory retrieval and decision recording."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from backend.memory import shared_memory as storage

from backend.memory.shared_memory import (
    CONTRACT_FILE, DECISIONS_FILE, ERRORS_FILE, FIXES_FILE, OUTPUT_FILE,
    PLAN_FILE, PROJECT_FILE, VERIFICATION_FILE, WORKSPACE_DIR,
    append_json_list, read_json,
)

FIELDS: dict[str, tuple[str, ...]] = {
    "Requirements": (),
    "Architecture": ("app_name", "description", "inputs", "outputs", "edge_cases", "project_name", "project_type", "design_direction"),
    "Coder": ("app_name", "description", "inputs", "outputs", "edge_cases", "project_name", "project_type", "design_direction"),
    "Test Writer": ("description", "inputs", "outputs", "edge_cases", "project_name", "project_type", "design_direction"),
    "Executor": ("project_name", "project_type"),
    "Self-Healing": ("description", "inputs", "outputs", "edge_cases", "project_name", "project_type", "design_direction"),
    "Verifier": ("description", "inputs", "outputs", "edge_cases", "project_name", "project_type", "design_direction"),
    "Doc Agent": ("app_name", "description", "project_name", "project_type", "design_direction"),
}
FILES: dict[str, tuple[str, ...]] = {
    "Requirements": (), "Architecture": (), "Coder": ("main.py", "test_main.py"),
    "Test Writer": ("main.py",), "Executor": ("main.py", "test_main.py"),
    "Self-Healing": ("main.py", "test_main.py"),
    "Verifier": ("main.py", "test_main.py"), "Doc Agent": ("main.py", "test_main.py"),
}


class MemoryManager:
    """Filter the shared blackboard by agent and recent history."""

    @staticmethod
    def _recent_for(path: str | Path, task: dict[str, Any]) -> list[dict[str, Any]]:
        """Keep two recent records whose file and feature tags fit this task."""
        file_path = str(task.get("file_path", "")).lower()
        feature = str(task.get("feature", "")).lower()
        records = read_json(path, [])
        if not isinstance(records, list):
            return []
        relevant = []
        for item in records:
            if not isinstance(item, dict):
                continue
            tagged_file = str(item.get("file", "")).lower()
            tagged_feature = str(item.get("feature", "")).lower()
            if file_path and tagged_file and file_path not in tagged_file:
                continue
            if feature and tagged_feature and feature not in tagged_feature:
                continue
            relevant.append(item)
        return relevant[-2:]

    def get_for_agent(self, agent_name: str, task: dict[str, Any]) -> dict[str, Any]:
        """Return only the contract, plan, files, and recent events needed by an agent."""
        contract = read_json(storage.CONTRACT_FILE)
        plan = read_json(storage.PLAN_FILE)
        project_name = str(contract.get("project_name", ""))
        project_type = contract.get("project_type", "python_cli")
        planned = [item.get("path") for item in plan.get("file_structure", [])
                   if isinstance(item, dict) and isinstance(item.get("path"), str)]
        source = [name for name in planned if name not in {"test_main.py", "README.md"}]
        if not planned:
            allowed = FILES.get(agent_name, ())
        elif agent_name == "Coder":
            allowed = source + (["test_main.py"] if project_type == "python_cli" else [])
        elif agent_name == "Test Writer":
            allowed = source
        elif agent_name == "Self-Healing":
            allowed = source + (["test_main.py"] if project_type == "python_cli" else [])
        elif agent_name in {"Executor", "Verifier", "Doc Agent"}:
            allowed = [*source, "test_main.py"]
        else:
            allowed = FILES.get(agent_name, ())
        root = storage.WORKSPACE_DIR / project_name if project_name else None
        files = {name: (root / name).read_text(encoding="utf-8") for name in allowed
                 if root is not None and (root / name).is_file()}
        keys = FIELDS.get(agent_name, ())
        selected_plan = plan if agent_name in {"Coder", "Test Writer", "Verifier", "Doc Agent", "Executor", "Self-Healing"} else {}
        if agent_name == "Architecture":
            selected_plan = {}
        return {
            "contract": {key: contract[key] for key in keys if key in contract},
            "plan": selected_plan,
            "files": files,
            "allowed_files": list(allowed),
            "errors": self._recent_for(storage.ERRORS_FILE, task),
            "fixes": self._recent_for(storage.FIXES_FILE, task),
            "output": read_json(storage.OUTPUT_FILE) if agent_name == "Verifier" else {},
            "verification": read_json(storage.VERIFICATION_FILE) if agent_name == "Doc Agent" else {},
            "task": task,
        }

    def remember_decision(self, agent: str, decision: str, reason: str) -> None:
        """Record a tagged decision without copying whole agent prompts."""
        project = read_json(storage.PROJECT_FILE)
        append_json_list(storage.DECISIONS_FILE, {
            "agent": agent, "decision": decision, "reason": reason,
            "feature": project.get("idea", "")[:120], "file": "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def summarize_session(self) -> str:
        """Compress the current project into a short, stable status sentence."""
        state = read_json(storage.PROJECT_FILE)
        contract = read_json(storage.CONTRACT_FILE)
        plan = read_json(storage.PLAN_FILE)
        return (f"Project: {contract.get('app_name', state.get('idea', 'Untitled'))}. "
                f"Phase: {state.get('phase', 'new')}. "
                f"Approved: {bool(state.get('approved'))}. "
                f"Criteria: {len(plan.get('acceptance_criteria', []))}. "
                f"Recent errors: {len(read_json(storage.ERRORS_FILE, [])[-2:])}.")


memory_manager = MemoryManager()

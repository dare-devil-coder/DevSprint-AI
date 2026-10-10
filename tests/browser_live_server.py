# Serve an isolated real-provider pipeline with one explicit test fault injection.
"""Run real model and SerpApi calls without touching saved user projects."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn

from backend import main, orchestrator as orchestration, serpapi_client
from backend.agents import (
    architecture_agent, coder_agent, doc_agent, executor_agent, requirements_agent,
    self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.memory import project_details, shared_memory


def configure(root: Path) -> None:
    """Point the real app at isolated data and inject one missing import."""
    memory = root / "memory"
    workspace = root / "workspace"
    memory.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    paths = {name: memory / filename for name, filename in {
        "CONTRACT_FILE": "contract.json", "PLAN_FILE": "plan.json",
        "VERIFICATION_FILE": "verification.json", "ERRORS_FILE": "errors.json",
        "FIXES_FILE": "fixes.json", "OUTPUT_FILE": "output.json",
        "PROJECT_FILE": "project.json", "SERPAPI_CACHE_FILE": "serpapi_cache.json",
        "SERPAPI_LOG_FILE": "serpapi_log.json", "DECISIONS_FILE": "decisions.json",
        "PROJECT_DETAILS_CACHE_FILE": "project_details_cache.json",
        "SETTINGS_FILE": "settings.json",
    }.items()}
    modules = (
        shared_memory, orchestration, main, serpapi_client, requirements_agent,
        architecture_agent, coder_agent, test_writer_agent, executor_agent,
        self_healing_agent, verifier_agent, doc_agent, project_details,
    )
    for module in modules:
        for name, path in paths.items():
            if hasattr(module, name):
                setattr(module, name, path)
        if hasattr(module, "WORKSPACE_DIR"):
            setattr(module, "WORKSPACE_DIR", workspace)
        if hasattr(module, "MEMORY_DIR"):
            setattr(module, "MEMORY_DIR", memory)

    original_run = coder_agent.CoderAgent.run
    fault_pending = True

    async def run_with_fault(self: coder_agent.CoderAgent,
                             context: dict[str, Any]) -> dict[str, Any]:
        """Make the first generated CLI fail once to exercise live repair."""
        nonlocal fault_pending
        result = await original_run(self, context)
        if fault_pending:
            contract = shared_memory.read_json(paths["CONTRACT_FILE"])
            source = workspace / contract["project_name"] / "main.py"
            lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
            insertion = max((index + 1 for index, line in enumerate(lines)
                             if line.lstrip().startswith("from __future__ import ")),
                            default=0)
            lines.insert(insertion,
                         "import devsprint_missing_dependency_for_browser_e2e\n")
            source.write_text(
                "".join(lines), encoding="utf-8",
            )
            fault_pending = False
        return result

    coder_agent.CoderAgent.run = run_with_fault
    main.orchestrator = orchestration.Orchestrator()
    original_start = main.orchestrator.start

    async def start_with_fault(idea: str) -> dict[str, Any]:
        """Rearm the single injected error for each fresh browser project."""
        nonlocal fault_pending
        state = await original_start(idea)
        fault_pending = True
        return state

    main.orchestrator.start = start_with_fault


if __name__ == "__main__":
    configure(Path("demo_evidence/live_runtime"))
    uvicorn.run(main.app, host="127.0.0.1", port=8002, log_level="warning")

# Run generated code and tests, retaining output and execution failures.
"""Run generated code and tests, retaining output and execution failures."""

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from backend.agents.base_agent import BaseAgent
from backend.memory.shared_memory import (
    CONTRACT_FILE, ERRORS_FILE, OUTPUT_FILE, WORKSPACE_DIR, append_json_list,
    read_json, write_json,
)
from backend.utils.sandbox import run_python, run_tests


class ExecutorAgent(BaseAgent):
    """Execute one generated project inside its workspace directory."""

    def __init__(self) -> None:
        """Name the execution agent."""
        super().__init__("Executor", "executor")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run main.py and pytest with independent, bounded subprocesses."""
        contract = read_json(CONTRACT_FILE)
        root = WORKSPACE_DIR / contract["project_name"]
        timeout = max(1, min(int(os.getenv("SANDBOX_TIMEOUT", "30")), 120))
        execution = await asyncio.to_thread(run_python, "main.py", str(root), timeout)
        tests = await asyncio.to_thread(run_tests, root, timeout) if execution["success"] else None
        success = execution["success"] and (tests is None or tests["success"])
        output = (execution["stdout"] + ("\n" + tests["stdout"] if tests else "")).strip()
        error = (execution["stderr"] + ("\n" + tests["stderr"] if tests else "")).strip()
        if tests and not tests["success"] and not error:
            error = tests["stdout"]
        result = {"success": success, "output": output, "error": error,
                  "exit_code": execution["exit_code"],
                  "attempt": context.get("attempt", 1)}
        write_json(OUTPUT_FILE, result)
        if not success:
            append_json_list(ERRORS_FILE, {
                "agent": self.name, "error": error or "Process failed without an error message.",
                "traceback": "", "timestamp": datetime.now(timezone.utc).isoformat(),
                "attempt": result["attempt"],
            })
        result["message"] = "Execution passed" if success else "Execution failed"
        return result

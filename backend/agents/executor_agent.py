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
from backend.utils.sandbox import run_python, run_tests, run_web_checks


class ExecutorAgent(BaseAgent):
    """Execute one generated project inside its workspace directory."""

    def __init__(self) -> None:
        """Name the execution agent."""
        super().__init__("Executor", "executor")

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run CLI help and pytest with independent, bounded subprocesses."""
        contract = context["memory"]["contract"] if "memory" in context else read_json(CONTRACT_FILE)
        root = WORKSPACE_DIR / contract["project_name"]
        timeout = max(1, min(int(os.getenv("SANDBOX_TIMEOUT", "30")), 120))
        if contract.get("project_type", "python_cli") == "web_app":
            tests = await asyncio.to_thread(run_tests, root, timeout)
            prototype = await asyncio.to_thread(run_web_checks, root, min(timeout, 15))
            success = tests["success"] and prototype["success"]
            output = (tests["stdout"] + "\n" + prototype["stdout"]).strip()
            error_parts = [tests["stdout"] if not tests["success"] else "",
                           tests["stderr"], prototype["stderr"]]
            exit_code = tests["exit_code"] if not tests["success"] else prototype["exit_code"]
        else:
            execution = await asyncio.to_thread(run_python, "main.py", str(root), timeout,
                                                ("--help",))
            tests = await asyncio.to_thread(run_tests, root, timeout) if execution["success"] else None
            success = execution["success"] and (tests is None or tests["success"])
            output = (execution["stdout"] + ("\n" + tests["stdout"] if tests else "")).strip()
            error_parts = [execution["stderr"]]
            if tests:
                if not tests["success"]:
                    error_parts.append(tests["stdout"])
                error_parts.append(tests["stderr"])
            exit_code = execution["exit_code"]
        error = "\n".join(part for part in error_parts if part).strip()
        result = {"success": success, "output": output, "error": error,
                  "exit_code": exit_code,
                  "attempt": context.get("attempt", 1)}
        write_json(OUTPUT_FILE, result)
        if not success:
            append_json_list(ERRORS_FILE, {
                "agent": self.name, "error": error or "Process failed without an error message.",
                "feature": "execution", "file": (
                    "index.html, styles.css, app.js, test_main.py"
                    if contract.get("project_type") == "web_app" else "main.py or test_main.py"),
                "traceback": "", "timestamp": datetime.now(timezone.utc).isoformat(),
                "attempt": result["attempt"],
            })
        result["message"] = "Execution passed" if success else "Execution failed"
        return result

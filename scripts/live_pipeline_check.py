# Rehearse the full real-model pipeline in isolated temporary project storage.
"""Live, approval-gated DevSprint smoke test without touching saved projects."""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from backend import orchestrator as orchestration, serpapi_client
from backend.agents import (
    architecture_agent, base_agent, coder_agent, doc_agent, executor_agent,
    requirements_agent, self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.memory import project_details, shared_memory


def isolate(root: Path) -> None:
    """Redirect all memory, workspace, and search logs to one temporary root."""
    memory = root / "memory"
    workspace = root / "workspace"
    memory.mkdir()
    workspace.mkdir()
    paths = {name: memory / filename for name, filename in {
        "CONTRACT_FILE": "contract.json", "PLAN_FILE": "plan.json",
        "VERIFICATION_FILE": "verification.json", "ERRORS_FILE": "errors.json",
        "FIXES_FILE": "fixes.json", "OUTPUT_FILE": "output.json",
        "PROJECT_FILE": "project.json", "SERPAPI_CACHE_FILE": "serpapi_cache.json",
        "SERPAPI_LOG_FILE": "serpapi_log.json", "DECISIONS_FILE": "decisions.json",
        "PROJECT_DETAILS_CACHE_FILE": "project_details_cache.json",
        "SETTINGS_FILE": "settings.json",
    }.items()}
    modules = (shared_memory, orchestration, serpapi_client, base_agent,
               requirements_agent, architecture_agent, coder_agent, test_writer_agent,
               executor_agent, self_healing_agent, verifier_agent, doc_agent,
               project_details)
    for module in modules:
        for name, path in paths.items():
            if hasattr(module, name):
                setattr(module, name, path)
        if hasattr(module, "WORKSPACE_DIR"):
            setattr(module, "WORKSPACE_DIR", workspace)
        if hasattr(module, "MEMORY_DIR"):
            setattr(module, "MEMORY_DIR", memory)


def review_generated_code(root: Path) -> None:
    """Parse generated files and reject dynamic code execution calls."""
    contract = shared_memory.read_json(shared_memory.CONTRACT_FILE)
    project = root / "workspace" / contract["project_name"]
    blocked_calls = {"eval", "exec", "open", "compile", "__import__"}
    for name in ("main.py", "test_main.py"):
        tree = ast.parse((project / name).read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in blocked_calls:
                    raise RuntimeError(f"Generated {name} contains a blocked call.")


async def run_live(root: Path) -> None:
    """Run the real agent pipeline and report its outcome and elapsed time."""
    isolate(root)
    original_run = executor_agent.ExecutorAgent.run

    async def guarded_run(self: executor_agent.ExecutorAgent,
                          context: dict[str, Any]) -> dict[str, Any]:
        """Review generated source before delegating to the real executor."""
        review_generated_code(root)
        result = await original_run(self, context)
        if not result["success"]:
            print(f"execution_attempt={context.get('attempt')} exit_code={result.get('exit_code')} "
                  f"output={ascii(result.get('output', '')[:900])} "
                  f"error={ascii(result.get('error', '')[:900])}", flush=True)
        return result

    executor_agent.ExecutorAgent.run = guarded_run
    original_test_generation = test_writer_agent.generate_json

    async def inspect_tests(system: str, user: str, **kwargs: Any) -> dict[str, Any]:
        """Record generated acceptance labels and functions for failure diagnosis."""
        data = await original_test_generation(system, user, **kwargs)
        source = str(data.get("test_main.py", ""))
        labels = [line.strip() for line in source.splitlines() if "# Acceptance:" in line]
        functions = [line.strip() for line in source.splitlines() if line.lstrip().startswith("def test_")]
        print(f"generated_test_labels={ascii(labels)} functions={ascii(functions)}", flush=True)
        return data

    test_writer_agent.generate_json = inspect_tests
    original_verification = verifier_agent.VerifierAgent.run

    async def inspect_verification(self: verifier_agent.VerifierAgent,
                                   context: dict[str, Any]) -> dict[str, Any]:
        """Show the precise evidence gaps that trigger a revision."""
        result = await original_verification(self, context)
        print(f"verification_gaps={ascii(result['gaps'])}", flush=True)
        return result

    verifier_agent.VerifierAgent.run = inspect_verification
    shared_memory.write_json(shared_memory.SETTINGS_FILE, {
        "generate_project_details": True, "skill_level": "beginner",
    })
    pipeline = orchestration.Orchestrator()
    started = time.perf_counter()
    await pipeline.start("Build me a CLI tool that converts Celsius to Fahrenheit")
    for answer in ("Temperature converter", "One Celsius number", "Fahrenheit number",
                   "Reject non-numeric input and show a clear error"):
        await pipeline.answer(answer)
    if pipeline._task is None:
        raise RuntimeError("Planning task did not start.")
    await asyncio.wait_for(pipeline._task, timeout=180)
    planning = pipeline.status()
    contract = shared_memory.read_json(shared_memory.CONTRACT_FILE)
    plan = shared_memory.read_json(shared_memory.PLAN_FILE)
    print(f"planning_phase={planning.get('phase')} elapsed_seconds={time.perf_counter() - started:.1f}", flush=True)
    print(f"planned_features={ascii([item.get('feature') for item in plan.get('acceptance_criteria', [])])}", flush=True)
    if planning.get("phase") != "awaiting_approval":
        raise RuntimeError(f"Planning failed: {str(planning.get('message', ''))[:180]}")
    if not contract.get("project_name") or not plan.get("acceptance_criteria"):
        raise RuntimeError("Contract or acceptance criteria are incomplete.")
    await pipeline.approve(True)
    if pipeline._task is None:
        raise RuntimeError("Build task did not start.")
    await asyncio.wait_for(pipeline._task, timeout=240)
    elapsed = time.perf_counter() - started
    state = pipeline.status()
    verification = shared_memory.read_json(shared_memory.VERIFICATION_FILE)
    output = shared_memory.read_json(shared_memory.OUTPUT_FILE)
    search = shared_memory.read_json(shared_memory.SERPAPI_LOG_FILE, {"calls": []})
    levels = project_details.list_details()
    print(f"final_phase={state.get('phase')} elapsed_seconds={elapsed:.1f}", flush=True)
    print(f"execution_passed={output.get('success')} verification={verification.get('summary', {})}", flush=True)
    print(f"initial_details={levels} serpapi_calls={len(search.get('calls', []))}", flush=True)
    if state.get("phase") != "complete" or not output.get("success") or len(levels) != 2:
        raise RuntimeError(f"Live pipeline incomplete: {str(state.get('message', ''))[:180]}")
    for depth in (3, 4):
        await asyncio.wait_for(project_details.generate(depth), timeout=90)
    print(f"on_demand_details={project_details.list_details()}", flush=True)


def main() -> None:
    """Create and clean an isolated temporary rehearsal directory."""
    if "--one-attempt" in sys.argv:
        os.environ["MAX_RETRIES"] = "0"
    with TemporaryDirectory(prefix="devsprint-live-") as location:
        asyncio.run(run_live(Path(location)))


if __name__ == "__main__":
    main()

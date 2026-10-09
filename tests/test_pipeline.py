# Exercise the approval pause, SerpApi repair, verification retry, and documentation.

import asyncio
from pathlib import Path

import pytest

from backend import orchestrator as orchestration
from backend.agents import (
    architecture_agent, coder_agent, doc_agent, executor_agent, requirements_agent,
    self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.memory import shared_memory


@pytest.mark.asyncio
async def test_full_pipeline_waits_repairs_revises_and_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A project may build only after approval, then repair and close a verifier gap."""
    memory = tmp_path / "memory"
    workspace = tmp_path / "workspace"
    memory.mkdir()
    workspace.mkdir()
    paths = {name: memory / filename for name, filename in {
        "CONTRACT_FILE": "contract.json", "PLAN_FILE": "plan.json",
        "VERIFICATION_FILE": "verification.json", "ERRORS_FILE": "errors.json",
        "FIXES_FILE": "fixes.json", "OUTPUT_FILE": "output.json",
        "PROJECT_FILE": "project.json", "SERPAPI_CACHE_FILE": "serpapi_cache.json",
        "SERPAPI_LOG_FILE": "serpapi_log.json",
    }.items()}
    modules = (shared_memory, orchestration, requirements_agent, architecture_agent,
               coder_agent, test_writer_agent, executor_agent, self_healing_agent,
               verifier_agent, doc_agent)
    for module in modules:
        for name, path in paths.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, path)
        if hasattr(module, "WORKSPACE_DIR"):
            monkeypatch.setattr(module, "WORKSPACE_DIR", workspace)

    calls = []
    broken = {"main.py": "raise RuntimeError('deliberate failure')\n",
              "test_main.py": "def test_initial():\n    assert True\n"}
    fixed = {"main.py": "def convert(c):\n    return c * 9 / 5 + 32\n\nif __name__ == '__main__':\n    print(convert(0))\n",
             "test_main.py": "def test_initial():\n    assert True\n"}
    acceptance_test = {
        "test_main.py": "from main import convert\n\n# Acceptance: Freezing conversion\n"
                        "def test_freezing_conversion():\n    assert convert(0) == 32\n",
    }

    async def fake_generate_json(system: str, user: str) -> dict:
        """Return representative artifacts for each agent call in sequence."""
        calls.append(system)
        index = len(calls)
        if index == 1:
            return {"app_name": "Temperature CLI", "description": "Convert Celsius to Fahrenheit",
                    "inputs": ["Celsius"], "outputs": ["Fahrenheit"],
                    "edge_cases": ["invalid input"]}
        if index == 2:
            return {"project_name": "temperature_cli",
                    "tech_stack": {"language": "python", "libraries": ["pytest"]},
                    "file_structure": [
                        {"path": "main.py", "purpose": "Convert values", "depends_on": []},
                        {"path": "test_main.py", "purpose": "Test conversion",
                         "depends_on": ["main.py"]},
                    ], "build_order": ["main.py", "test_main.py"],
                    "acceptance_criteria": [{"feature": "Freezing conversion",
                                             "given": "zero Celsius", "when": "converted",
                                             "then": "returns 32 Fahrenheit"}], "risks": []}
        if index == 3:
            return broken
        if index == 4:
            return acceptance_test
        if index == 5:
            return fixed
        if index == 6:
            return {"features": [{"feature": "Freezing conversion",
                                  "status": "partial", "evidence": "Review the edge case."}]}
        if index == 7:
            return fixed
        if index == 8:
            return acceptance_test
        return {"features": [{"feature": "Freezing conversion", "status": "pass",
                              "evidence": "return c * 9 / 5 + 32"}]}

    def fake_search(error: str, language: str) -> list[dict[str, str]]:
        """Record one synthetic SerpApi search without network access."""
        shared_memory.append_json_list(paths["SERPAPI_LOG_FILE"], {
            "query": f"{language} {error[:30]} fix", "results_count": 1,
            "cached": False, "error_context": error,
        }, key="calls")
        return [{"title": "RuntimeError fix", "snippet": "Remove deliberate failure",
                 "link": "https://example.test/fix"}]

    for module in (requirements_agent, architecture_agent, coder_agent,
                   test_writer_agent, self_healing_agent, verifier_agent):
        monkeypatch.setattr(module, "generate_json", fake_generate_json)
    monkeypatch.setattr(self_healing_agent, "search_for_fix", fake_search)
    monkeypatch.setenv("MAX_RETRIES", "5")
    pipeline = orchestration.Orchestrator()
    state = await pipeline.start("Build me a Celsius to Fahrenheit CLI")
    assert state["question"] == requirements_agent.QUESTIONS[0]
    with pytest.raises(RuntimeError, match="not waiting"):
        await pipeline.approve(True)
    for index, answer in enumerate(("A temperature converter", "A Celsius number",
                                    "A Fahrenheit number", "Reject invalid values")):
        state = await pipeline.answer(answer)
        if index < 3:
            assert state["question"] == requirements_agent.QUESTIONS[index + 1]
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=30)
    assert pipeline.status()["phase"] == "awaiting_approval"
    assert shared_memory.read_json(paths["PLAN_FILE"])["build_order"] == [
        "main.py", "test_main.py",
    ]
    assert not (workspace / "temperature_cli" / "main.py").exists()
    with pytest.raises(RuntimeError, match="must be true"):
        await pipeline.approve(False)
    await pipeline.approve(True)
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=45)
    assert pipeline.status()["phase"] == "complete"
    assert pipeline.status()["verification_retry"] == 1
    assert shared_memory.read_json(paths["OUTPUT_FILE"])["success"] is True
    assert len(shared_memory.read_json(paths["ERRORS_FILE"], [])) == 1
    assert len(shared_memory.read_json(paths["FIXES_FILE"], [])) == 1
    assert len(shared_memory.read_json(paths["SERPAPI_LOG_FILE"])["calls"]) == 1
    assert not shared_memory.read_json(paths["VERIFICATION_FILE"])["gaps"]
    assert (workspace / "temperature_cli" / "README.md").exists()
    assert "Known limitations" in (workspace / "temperature_cli" / "README.md").read_text()


@pytest.mark.asyncio
async def test_verification_stops_after_three_revisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent gaps cannot trigger an unbounded Coder loop."""
    project_file = tmp_path / "project.json"
    monkeypatch.setattr(orchestration, "PROJECT_FILE", project_file)
    state = {"idea": "A small tool", "answers": ["x"] * 4, "phase": "building",
             "agent": "Coder", "approved": True, "completed_agents": []}
    shared_memory.write_json(project_file, state)
    pipeline = orchestration.Orchestrator()
    calls = {"coder": 0, "doc": 0}

    async def code(context: dict, message: str = "") -> dict:
        """Count each initial build and verifier-requested revision."""
        calls["coder"] += 1
        return {"files": ["main.py", "test_main.py"]}

    async def simple(context: dict, message: str = "") -> dict:
        """Stand in for tests and execution that always pass."""
        return {"success": True}

    async def verify(context: dict, message: str = "") -> dict:
        """Return one persistent gap on every verification run."""
        report = {"layers": [], "features": [], "gaps": [
            {"feature": "output", "reason": "missing"},
        ]}
        return {"gaps": report["gaps"], "report": report}

    async def docs(context: dict, message: str = "") -> dict:
        """Track whether documentation incorrectly runs after failed verification."""
        calls["doc"] += 1
        return {}

    monkeypatch.setattr(pipeline.coder, "execute", code)
    monkeypatch.setattr(pipeline.test_writer, "execute", simple)
    monkeypatch.setattr(pipeline.executor, "execute", simple)
    monkeypatch.setattr(pipeline.verifier, "execute", verify)
    monkeypatch.setattr(pipeline.doc, "execute", docs)
    await pipeline._build(state)
    assert calls == {"coder": 4, "doc": 0}
    assert pipeline.status()["phase"] == "error"
    assert pipeline.status()["verification_retry"] == 3

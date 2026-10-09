# Check each Phase 1 agent's contract with isolated files and mocked services.

from pathlib import Path

import pytest

from backend.agents import (
    architecture_agent, coder_agent, doc_agent, executor_agent, requirements_agent,
    self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.memory.shared_memory import read_json, write_json


@pytest.mark.asyncio
async def test_requirements_rejects_invalid_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed model contract must not be passed to coding."""

    async def invalid(system: str, user: str) -> dict:
        """Return the wrong field shape for validation."""
        return {"app_name": "Tool", "description": "Test", "inputs": "wrong",
                "outputs": [], "edge_cases": []}

    monkeypatch.setattr(requirements_agent, "generate_json", invalid)
    monkeypatch.setattr(requirements_agent, "CONTRACT_FILE", tmp_path / "contract.json")
    with pytest.raises(ValueError, match="inputs"):
        await requirements_agent.RequirementsAgent().run({"idea": "A tool", "answers": ["a"] * 4})


def test_coder_rejects_missing_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The coder cannot persist a partial generated project."""
    monkeypatch.setattr(coder_agent, "WORKSPACE_DIR", tmp_path)
    with pytest.raises(ValueError, match="main.py"):
        coder_agent.write_code_files("sample", {"main.py": "print('hi')"})
    assert not (tmp_path / "sample").exists()


@pytest.mark.asyncio
async def test_executor_records_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A nonzero process result appears in both output and errors memory."""
    contract = tmp_path / "contract.json"
    errors = tmp_path / "errors.json"
    output = tmp_path / "output.json"
    write_json(contract, {"project_name": "sample"})
    (tmp_path / "sample").mkdir()
    monkeypatch.setattr(executor_agent, "CONTRACT_FILE", contract)
    monkeypatch.setattr(executor_agent, "ERRORS_FILE", errors)
    monkeypatch.setattr(executor_agent, "OUTPUT_FILE", output)
    monkeypatch.setattr(executor_agent, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(executor_agent, "run_python", lambda *args: {
        "success": False, "stdout": "", "stderr": "SyntaxError: invalid syntax", "exit_code": 1,
    })
    result = await executor_agent.ExecutorAgent().run({"attempt": 1})
    assert result["success"] is False
    assert read_json(output)["error"] == "SyntaxError: invalid syntax"
    assert read_json(errors, [])[0]["agent"] == "Executor"


@pytest.mark.asyncio
async def test_healer_uses_search_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The healer sends error and search evidence to generation, then writes a fix."""
    contract = tmp_path / "contract.json"
    errors = tmp_path / "errors.json"
    fixes = tmp_path / "fixes.json"
    write_json(contract, {"project_name": "sample", "description": "A CLI"})
    write_json(errors, [{"agent": "Executor", "error": "NameError: missing"}])
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("missing()\n", encoding="utf-8")
    (project / "test_main.py").write_text("def test_one(): assert True\n", encoding="utf-8")
    observed = []

    async def replacement(system: str, user: str) -> dict:
        """Verify grounded prompt context and provide repaired files."""
        observed.append(user)
        return {"main.py": "print('fixed')\n", "test_main.py": "def test_one(): assert True\n"}

    monkeypatch.setattr(self_healing_agent, "CONTRACT_FILE", contract)
    monkeypatch.setattr(self_healing_agent, "ERRORS_FILE", errors)
    monkeypatch.setattr(self_healing_agent, "FIXES_FILE", fixes)
    monkeypatch.setattr(self_healing_agent, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(coder_agent, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(self_healing_agent, "generate_json", replacement)
    monkeypatch.setattr(self_healing_agent, "search_for_fix", lambda *args: [
        {"title": "NameError guide", "snippet": "Define the name", "link": "https://example.test"}
    ])
    result = await self_healing_agent.SelfHealingAgent().run({"attempt": 1})
    assert result["fixed"] is True
    assert "NameError guide" in observed[0]
    assert "NameError: missing" in observed[0]
    assert (project / "main.py").read_text(encoding="utf-8") == "print('fixed')\n"
    assert len(read_json(fixes, [])) == 1


@pytest.mark.asyncio
async def test_architecture_rejects_extra_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plan must stay within the approved two-file Python scope."""
    contract = tmp_path / "contract.json"
    write_json(contract, {"project_name": "sample", "app_name": "Sample"})

    async def invalid(system: str, user: str) -> dict:
        """Return a plausible plan with an unauthorized third file."""
        return {"tech_stack": {"language": "python", "libraries": []},
                "file_structure": [{"path": name, "purpose": "source", "depends_on": []}
                                   for name in ("main.py", "test_main.py", "server.py")],
                "build_order": ["main.py", "test_main.py"],
                "acceptance_criteria": [{"feature": "Print greeting", "given": "input",
                                         "when": "run", "then": "output"}], "risks": []}

    monkeypatch.setattr(architecture_agent, "CONTRACT_FILE", contract)
    monkeypatch.setattr(architecture_agent, "PLAN_FILE", tmp_path / "plan.json")
    monkeypatch.setattr(architecture_agent, "generate_json", invalid)
    with pytest.raises(ValueError, match="main.py and test_main.py only"):
        await architecture_agent.ArchitectureAgent().run({})


@pytest.mark.asyncio
async def test_test_writer_requires_criterion_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests without a named acceptance mapping must be rejected."""
    contract = tmp_path / "contract.json"
    plan = tmp_path / "plan.json"
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("def greet(): return 'hi'\n", encoding="utf-8")
    write_json(contract, {"project_name": "sample"})
    write_json(plan, {"acceptance_criteria": [{"feature": "Greet"}]})

    async def unmapped(system: str, user: str) -> dict:
        """Return runnable pytest source with no criterion label."""
        return {"test_main.py": "def test_greet(): assert True\n"}

    monkeypatch.setattr(test_writer_agent, "CONTRACT_FILE", contract)
    monkeypatch.setattr(test_writer_agent, "PLAN_FILE", plan)
    monkeypatch.setattr(test_writer_agent, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(test_writer_agent, "generate_json", unmapped)
    with pytest.raises(ValueError, match="mapped pytest test"):
        await test_writer_agent.TestWriterAgent().run({})


@pytest.mark.asyncio
async def test_verifier_demotes_unfounded_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A model pass requires an exact excerpt from generated source."""
    contract, plan, output = (tmp_path / name for name in
                              ("contract.json", "plan.json", "output.json"))
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "test_main.py").write_text("def test_hi(): assert True\n", encoding="utf-8")
    write_json(contract, {"project_name": "sample"})
    write_json(plan, {"acceptance_criteria": [{"feature": "Greet"}]})
    write_json(output, {"success": True})

    async def unfounded(system: str, user: str) -> dict:
        """Claim a pass with source text that does not exist."""
        return {"features": [{"feature": "Greet", "status": "pass", "evidence": "invented()"}]}

    for name, value in (("CONTRACT_FILE", contract), ("PLAN_FILE", plan),
                        ("OUTPUT_FILE", output), ("VERIFICATION_FILE", tmp_path / "verification.json"),
                        ("WORKSPACE_DIR", tmp_path), ("generate_json", unfounded)):
        monkeypatch.setattr(verifier_agent, name, value)
    result = await verifier_agent.VerifierAgent().run({})
    assert result["report"]["features"][0]["status"] == "partial"
    assert len(result["gaps"]) == 1
    assert result["report"]["layers"][0]["status"] == "na"


@pytest.mark.asyncio
async def test_doc_agent_uses_verified_project_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The generated README must include feature and verified limitations."""
    contract, plan, report = (tmp_path / name for name in
                              ("contract.json", "plan.json", "verification.json"))
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "test_main.py").write_text("def test_hi(): assert True\n", encoding="utf-8")
    write_json(contract, {"project_name": "sample", "app_name": "Sample",
                          "description": "A greeting CLI"})
    write_json(plan, {"acceptance_criteria": [{"feature": "Greet"}],
                      "risks": ["Unicode terminal support varies"]})
    write_json(report, {"gaps": []})
    for name, value in (("CONTRACT_FILE", contract), ("PLAN_FILE", plan),
                        ("VERIFICATION_FILE", report), ("WORKSPACE_DIR", tmp_path)):
        monkeypatch.setattr(doc_agent, name, value)
    await doc_agent.DocAgent().run({})
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "# Sample" in readme
    assert "- Greet" in readme
    assert "Unicode terminal support varies" in readme

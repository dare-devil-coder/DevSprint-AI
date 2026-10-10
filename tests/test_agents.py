# Check each Phase 1 agent's contract with isolated files and mocked services.

from pathlib import Path
import runpy

import pytest

from backend.agents import (
    architecture_agent, coder_agent, doc_agent, executor_agent, requirements_agent,
    self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.agents.requirements_agent import infer_project_type, questions_for_project
from backend.memory.shared_memory import read_json, write_json
from backend.utils.sandbox import run_python
from backend.utils.sandbox import run_tests, run_web_checks


def test_requirements_questions_adapt_to_requested_project_format() -> None:
    """The first answer selects relevant web or CLI follow-up questions."""
    idea = "Build an app to track my reading list"
    web_questions = questions_for_project(idea, ["A browser-based web app"])
    cli_questions = questions_for_project(idea, ["A Python command-line tool"])
    assert "screens and actions" in web_questions[1]
    assert "commands or options" in cli_questions[1]
    assert infer_project_type(idea, ["A Python command-line tool"]) == "python_cli"
    assert infer_project_type(idea, ["A browser-based web app"]) == "web_app"


def test_web_project_smoke_checks_require_local_assets_and_semantic_html(tmp_path: Path) -> None:
    """The generated browser app has a real entry page and loadable local assets."""
    (tmp_path / "index.html").write_text(
        '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Reading list</title><link rel="stylesheet" href="styles.css"></head>'
        '<body><main><h1>Reading list</h1></main><script src="app.js"></script></body></html>',
        encoding="utf-8")
    (tmp_path / "styles.css").write_text("main { max-width: 48rem; }\n", encoding="utf-8")
    (tmp_path / "app.js").write_text("document.querySelector('main');\n", encoding="utf-8")
    result = run_web_checks(tmp_path)
    assert result["success"] is True, result


def test_generated_pytest_runs_without_unrelated_global_plugins(tmp_path: Path) -> None:
    """Nested acceptance runs stay local and do not initialize machine-wide plugins."""
    (tmp_path / "test_main.py").write_text(
        "def test_generated_output():\n    assert 'StudyFlow'.startswith('Study')\n",
        encoding="utf-8",
    )
    result = run_tests(tmp_path, 10)
    assert result["success"] is True, result
    assert "1 passed" in result["stdout"]


@pytest.mark.asyncio
async def test_requirements_rejects_invalid_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed model contract must not be passed to coding."""

    async def invalid(system: str, user: str, **kwargs: object) -> dict:
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


def test_coder_rejects_invalid_web_javascript() -> None:
    """Invalid generated JavaScript is rejected before it reaches Executor."""
    with pytest.raises(ValueError, match="invalid JavaScript syntax"):
        coder_agent.validate_code_files({
            "index.html": '<!doctype html><html><head><title>x</title><meta name="viewport"></head><body><main></main><link rel="stylesheet" href="styles.css"><script src="app.js"></script></body></html>',
            "styles.css": "main { color: blue; }",
            "app.js": "function load() { try {} } catch (error) {}",
        }, "web_app")


def test_coder_rejects_invalid_repair_before_overwriting_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed model response cannot destroy existing generated tests."""
    monkeypatch.setattr(coder_agent, "WORKSPACE_DIR", tmp_path)
    project = tmp_path / "sample"
    project.mkdir()
    (project / "test_main.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Python syntax"):
        coder_agent.write_code_files("sample", {
            "main.py": "print('ok')\n",
            "test_main.py": "def test_broken():\n    assert \\\"broken\n",
        })
    assert (project / "test_main.py").read_text(encoding="utf-8") == "def test_ok(): assert True\n"


def test_cli_help_smoke_accepts_required_positional_input(tmp_path: Path) -> None:
    """A healthy required-argument CLI passes help even when no-argument use fails."""
    (tmp_path / "main.py").write_text(
        "import argparse\nparser = argparse.ArgumentParser()\n"
        "parser.add_argument('temperature', type=float)\nparser.parse_args()\n",
        encoding="utf-8",
    )
    assert run_python("main.py", str(tmp_path), arguments=("--help",))["success"] is True
    assert run_python("main.py", str(tmp_path))["success"] is False


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
async def test_executor_passes_pytest_failure_to_healer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pytest assertion output reaches repair context even when stderr has a warning."""
    contract = tmp_path / "contract.json"
    errors = tmp_path / "errors.json"
    write_json(contract, {"project_name": "sample"})
    (tmp_path / "sample").mkdir()
    for name, value in (("CONTRACT_FILE", contract), ("ERRORS_FILE", errors),
                        ("OUTPUT_FILE", tmp_path / "output.json"),
                        ("WORKSPACE_DIR", tmp_path)):
        monkeypatch.setattr(executor_agent, name, value)
    monkeypatch.setattr(executor_agent, "run_python", lambda *args: {
        "success": True, "stdout": "usage: sample", "stderr": "", "exit_code": 0,
    })
    monkeypatch.setattr(executor_agent, "run_tests", lambda *args: {
        "success": False, "stdout": "FAILED test_main.py::test_convert\nAssertionError: 33 != 32",
        "stderr": "DeprecationWarning: plugin setting", "exit_code": 1,
    })
    result = await executor_agent.ExecutorAgent().run({"attempt": 1})
    assert result["success"] is False
    assert "AssertionError: 33 != 32" in result["error"]
    assert "DeprecationWarning" in result["error"]
    assert "AssertionError: 33 != 32" in read_json(errors, [])[0]["error"]


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

    async def replacement(system: str, user: str, **kwargs: object) -> dict:
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
async def test_healer_continues_when_serpapi_search_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing SerpApi access is recorded while model-based repair still proceeds."""
    contract, errors, fixes = (tmp_path / name for name in
                               ("contract.json", "errors.json", "fixes.json"))
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")
    write_json(contract, {"project_name": "sample", "description": "A CLI"})
    write_json(errors, [{"agent": "Executor", "error": "RuntimeError: broken"}])

    async def replacement(system: str, user: str, **kwargs: object) -> dict:
        assert '"search_results": []' in user
        return {"main.py": "print('repaired')\n",
                "test_main.py": "def test_repaired(): assert 'repaired' in 'repaired'\n"}

    def unavailable(*args: object) -> list[dict[str, str]]:
        raise RuntimeError("SERPAPI_API_KEY is missing")

    for name, value in (
        ("CONTRACT_FILE", contract), ("ERRORS_FILE", errors), ("FIXES_FILE", fixes),
        ("PLAN_FILE", tmp_path / "plan.json"), ("WORKSPACE_DIR", tmp_path),
        ("generate_json", replacement), ("search_for_fix", unavailable),
    ):
        monkeypatch.setattr(self_healing_agent, name, value)
    monkeypatch.setattr(coder_agent, "WORKSPACE_DIR", tmp_path)
    result = await self_healing_agent.SelfHealingAgent().run({"attempt": 1})
    assert result["fixed"] is True
    assert read_json(fixes)[0]["search_error"] == "SERPAPI_API_KEY is missing"


@pytest.mark.asyncio
async def test_architecture_rejects_extra_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The plan must stay within the approved two-file Python scope."""
    contract = tmp_path / "contract.json"
    write_json(contract, {"project_name": "sample", "app_name": "Sample"})

    async def invalid(system: str, user: str, **kwargs: object) -> dict:
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

    async def unmapped(system: str, user: str, **kwargs: object) -> dict:
        """Return runnable pytest source with no criterion label."""
        return {"test_main.py": "def test_greet(): assert greet() == 'hi'\n"}

    monkeypatch.setattr(test_writer_agent, "CONTRACT_FILE", contract)
    monkeypatch.setattr(test_writer_agent, "PLAN_FILE", plan)
    monkeypatch.setattr(test_writer_agent, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(test_writer_agent, "generate_json", unmapped)
    with pytest.raises(ValueError, match="mapped pytest test"):
        await test_writer_agent.TestWriterAgent().run({})


@pytest.mark.asyncio
async def test_test_writer_uses_labeled_source_smokes_when_providers_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider outage still yields executable, explicitly qualified smoke checks."""
    contract = tmp_path / "contract.json"
    plan = tmp_path / "plan.json"
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("def greet(): return 'hi'\n", encoding="utf-8")
    write_json(contract, {"project_name": "sample", "project_type": "python_cli"})
    write_json(plan, {"acceptance_criteria": [
        {"feature": "Inline Validation", "given": "The user leaves title blank",
         "when": "They submit the form", "then": "An inline error message appears"},
        {"feature": "Persistence", "given": "Tasks are modified",
         "when": "The user refreshes", "then": "Saved tasks restore from localStorage"},
    ]})
    (project / "main.py").write_text(
        "def greet(): return 'hi'\n"
        "def validate(): return 'Title is required. Invalid date.'\n"
        "STORAGE = 'localStorage'\n", encoding="utf-8")

    async def unavailable(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("No JSON-capable model is available for testing within the testing limit.")

    for name, value in (("CONTRACT_FILE", contract), ("PLAN_FILE", plan),
                        ("WORKSPACE_DIR", tmp_path), ("generate_json", unavailable)):
        monkeypatch.setattr(test_writer_agent, name, value)
    result = await test_writer_agent.TestWriterAgent().run({})
    generated = (project / "test_main.py").read_text(encoding="utf-8")
    assert "source-level smoke checks, not browser behavior tests" in generated
    assert "# Acceptance: Inline Validation" in generated
    assert "# Acceptance: Persistence" in generated
    assert "Provider tests unavailable" in result["message"]
    generated_tests = runpy.run_path(str(project / "test_main.py"))
    generated_tests["test_generated_sources_exist_and_are_nonempty"]()
    generated_tests["test_acceptance_source_signal_1"]()
    generated_tests["test_acceptance_source_signal_2"]()


@pytest.mark.asyncio
async def test_test_writer_accepts_mapping_above_decorator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An acceptance label remains attached to a parametrized pytest function."""
    contract = tmp_path / "contract.json"
    plan = tmp_path / "plan.json"
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("def convert(value): return value + 32\n", encoding="utf-8")
    write_json(contract, {"project_name": "sample"})
    write_json(plan, {"acceptance_criteria": [{"feature": "Convert temperatures"}]})

    async def mapped(system: str, user: str, **kwargs: object) -> dict:
        """Return a normal pytest decorator between the label and test."""
        return {"test_main.py": "import pytest\n\n# Acceptance: Convert temperatures\n"
                "@pytest.mark.parametrize('value', [0, 10])\n"
                "def test_convert(value):\n    assert convert(value) == value + 32\n"}

    for name, value in (("CONTRACT_FILE", contract), ("PLAN_FILE", plan),
                        ("WORKSPACE_DIR", tmp_path), ("generate_json", mapped)):
        monkeypatch.setattr(test_writer_agent, name, value)
    result = await test_writer_agent.TestWriterAgent().run({})
    assert result["test_count"] == 1


def test_test_writer_labels_clearly_named_tests() -> None:
    """Missing comments can be restored from unambiguous test function names."""
    criteria = [{"feature": "Addition operation"},
                {"feature": "Division by zero handling"}]
    data = {"test_main.py": "def test_addition():\n    assert 2 + 3 == 5\n\n"
            "def test_division_by_zero():\n    assert divide(1, 0) == 'error'\n"}
    test_writer_agent.add_missing_acceptance_labels(data, criteria)
    source, count = test_writer_agent.validate_generated_tests(data, criteria)
    assert count == 2
    assert "# Acceptance: Addition operation\ndef test_addition" in source
    assert "# Acceptance: Division by zero handling\ndef test_division_by_zero" in source


def test_test_writer_rejects_placeholder_assertions() -> None:
    """Placeholder tests must not pass acceptance validation."""
    with pytest.raises(ValueError, match="placeholder 'assert True'"):
        test_writer_agent.validate_generated_tests(
            {"test_main.py": "# Acceptance: Greet\ndef test_greet(): assert True\n"},
            [{"feature": "Greet"}],
        )


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

    async def unfounded(system: str, user: str, **kwargs: object) -> dict:
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
async def test_verifier_falls_back_when_all_models_are_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider outage still produces grounded results for every criterion."""
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    tests = (
        "# Acceptance: Greet the user\n"
        "def test_greeting():\n    greet = 'greeting'\n    assert greet in 'greeting'\n\n"
        "# Acceptance: Save the greeting\n"
        "def test_saved_greeting():\n    saved_greeting = 'greeting'\n"
        "    assert saved_greeting in 'greeting'\n"
    )
    (project / "test_main.py").write_text(tests, encoding="utf-8")
    contract = tmp_path / "contract.json"
    plan = tmp_path / "plan.json"
    output = tmp_path / "output.json"
    write_json(contract, {"project_name": "sample", "project_type": "python_cli"})
    write_json(plan, {
        "file_structure": [{"path": "main.py"}, {"path": "test_main.py"}],
        "acceptance_criteria": [
            {"feature": "Greet the user"}, {"feature": "Save the greeting"},
        ],
    })
    write_json(output, {"success": True})

    async def unavailable(system: str, user: str, **kwargs: object) -> dict:
        raise RuntimeError("No JSON-capable model is available for verification: provider timeout")

    for name, value in (
        ("CONTRACT_FILE", contract), ("PLAN_FILE", plan), ("OUTPUT_FILE", output),
        ("VERIFICATION_FILE", tmp_path / "verification.json"),
        ("WORKSPACE_DIR", tmp_path), ("generate_json", unavailable),
    ):
        monkeypatch.setattr(verifier_agent, name, value)

    result = await verifier_agent.VerifierAgent().run({})
    assert [feature["status"] for feature in result["report"]["features"]] == ["pass", "pass"]
    assert "assert greet in 'greeting'" in result["report"]["features"][0]["evidence"]
    assert result["gaps"] == []


def test_verifier_finds_exact_assertion_for_mapped_feature() -> None:
    """A passing labeled test can supply exact source evidence for a feature."""
    source = "# Acceptance: Convert Celsius\ndef test_zero():\n    assert convert(0) == 32\n"
    assert verifier_agent.mapped_assertion(source, "Convert Celsius") == "assert convert(0) == 32"
    assert verifier_agent.mapped_assertion(source, "Other feature") is None
    unrelated = "# Acceptance: Save tasks\ndef test_save():\n    assert 2 + 2 == 4\n"
    assert verifier_agent.mapped_assertion(unrelated, "Save tasks") is None


@pytest.mark.asyncio
async def test_doc_agent_uses_verified_project_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The generated README must include feature and verified limitations."""
    contract, plan, report = (tmp_path / name for name in
                              ("contract.json", "plan.json", "verification.json"))
    project = tmp_path / "sample"
    project.mkdir()
    (project / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "test_main.py").write_text(
        "# Deterministic fallback: source-level smoke checks, not browser behavior tests.\n"
        "def test_hi(): assert 'hi' in 'hi'\n", encoding="utf-8")
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
    assert "source-level signals" in readme

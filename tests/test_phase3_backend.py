# Verify scoped memory, skill disclosure, explanation depth, and demo reset.
"""Phase 3 backend behavior tests."""

from pathlib import Path
import asyncio

import pytest

from backend import orchestrator as orchestration
from backend.memory import project_details, shared_memory
from backend.memory.memory_manager import MemoryManager
from backend.skills.skill_manager import SkillManager
from tests import browser_demo_server


def test_memory_context_is_scoped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Agents receive limited contract fields, allowed files, and two recent events."""
    memory = tmp_path / "memory"
    workspace = tmp_path / "workspace"
    memory.mkdir()
    project = workspace / "sample"
    project.mkdir(parents=True)
    for name, content in (("main.py", "print(1)"), ("test_main.py", "assert True"),
                          ("secret.txt", "excluded")):
        (project / name).write_text(content, encoding="utf-8")
    paths = {"CONTRACT_FILE": memory / "contract.json", "PLAN_FILE": memory / "plan.json",
             "ERRORS_FILE": memory / "errors.json", "FIXES_FILE": memory / "fixes.json"}
    for key, path in paths.items():
        monkeypatch.setattr(shared_memory, key, path)
    monkeypatch.setattr(shared_memory, "WORKSPACE_DIR", workspace)
    shared_memory.write_json(paths["CONTRACT_FILE"], {"project_name": "sample", "app_name": "Sample",
                                                      "description": "Example", "private": "excluded"})
    shared_memory.write_json(paths["PLAN_FILE"], {"acceptance_criteria": []})
    shared_memory.write_json(paths["ERRORS_FILE"], [{"error": str(index)} for index in range(4)])
    shared_memory.write_json(paths["FIXES_FILE"], [{"fix": str(index)} for index in range(4)])
    context = MemoryManager().get_for_agent("Test Writer", {"task": "tests"})
    assert "private" not in context["contract"]
    assert context["files"] == {"main.py": "print(1)"}
    assert context["errors"] == [{"error": "2"}, {"error": "3"}]
    assert context["fixes"] == [{"fix": "2"}, {"fix": "3"}]


def test_memory_events_filter_file_tags_before_recent_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An agent receives two relevant events even after unrelated newer errors."""
    errors = tmp_path / "errors.json"
    fixes = tmp_path / "fixes.json"
    shared_memory.write_json(errors, [
        {"error": "first", "file": "main.py"},
        {"error": "second", "file": "main.py"},
        {"error": "unrelated", "file": "README.md"},
    ])
    shared_memory.write_json(fixes, [])
    monkeypatch.setattr(shared_memory, "ERRORS_FILE", errors)
    monkeypatch.setattr(shared_memory, "FIXES_FILE", fixes)
    assert MemoryManager._recent_for(errors, {"file_path": "main.py"}) == [
        {"error": "first", "file": "main.py"},
        {"error": "second", "file": "main.py"},
    ]


def test_skill_metadata_and_task_activation() -> None:
    """Metadata excludes bodies while Python and test tasks activate matching skills."""
    manager = SkillManager()
    metadata = manager.list_skills()
    assert len(metadata) == 3
    assert all("body" not in item and "token_cost" in item for item in metadata)
    coder = manager.load_skills_for({"language": "python", "file_path": "main.py"})
    assert "python_best_practices" in [item["name"] for item in coder]
    tests = manager.load_skills_for({"language": "python", "file_path": "test_main.py"})
    assert "testing_patterns" in manager.get_active_skill_names()
    assert all(item["body"] for item in tests)


@pytest.mark.asyncio
async def test_project_details_use_cheap_model_cache_and_on_demand_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Initial levels use the cheap model and repeat generation reuses hashes."""
    project = tmp_path / "workspace" / "sample"
    project.mkdir(parents=True)
    (project / "main.py").write_text("print('hello')\n", encoding="utf-8")
    contract = tmp_path / "contract.json"
    plan = tmp_path / "plan.json"
    cache = tmp_path / "cache.json"
    shared_memory.write_json(contract, {"project_name": "sample", "description": "Say hello"})
    shared_memory.write_json(plan, {"tech_stack": {"language": "python"}})
    for key, value in (("CONTRACT_FILE", contract), ("PLAN_FILE", plan),
                       ("PROJECT_DETAILS_CACHE_FILE", cache),
                       ("WORKSPACE_DIR", project.parent)):
        monkeypatch.setattr(project_details, key, value)
    calls: list[str | None] = []

    async def explanation(system: str, user: str, model: str | None = None,
                          capability: str | None = None) -> dict[str, str]:
        """Record model selection and return a usable explanation."""
        calls.append(model)
        return {"explanation": "This file prints a greeting."}

    monkeypatch.setattr(project_details, "generate_json", explanation)
    monkeypatch.setenv("OPENAI_MODEL_CHEAP", "cheap-test-model")
    assert len(await project_details.generate()) == 2
    assert calls == ["cheap-test-model", "cheap-test-model"]
    await project_details.generate()
    assert len(calls) == 2
    assert len(await project_details.generate(3)) == 3
    assert calls[-1] is None
    assert "level_4_technical.md" not in project_details.list_details()


@pytest.mark.asyncio
async def test_demo_reset_removes_generated_data_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clean demo preserves scaffold markers and removes generated artifacts."""
    memory = tmp_path / "memory"
    workspace = tmp_path / "workspace"
    memory.mkdir()
    workspace.mkdir()
    (memory / ".gitkeep").write_text("", encoding="utf-8")
    (workspace / ".gitkeep").write_text("", encoding="utf-8")
    (memory / "project.json").write_text("{}", encoding="utf-8")
    (workspace / "sample").mkdir()
    monkeypatch.setattr(orchestration, "MEMORY_DIR", memory)
    monkeypatch.setattr(orchestration, "WORKSPACE_DIR", workspace)
    result = await orchestration.Orchestrator().demo_reset()
    assert result == {"status": "ready"}
    assert sorted(path.name for path in memory.iterdir()) == [".gitkeep"]
    assert sorted(path.name for path in workspace.iterdir()) == [".gitkeep"]


@pytest.mark.asyncio
async def test_mock_browser_pipeline_generates_project_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The isolated browser demo completes and writes both default learner levels."""
    from backend import main
    from backend.agents import (
        architecture_agent, coder_agent, doc_agent, executor_agent,
        requirements_agent, self_healing_agent, test_writer_agent, verifier_agent,
    )

    modules = (shared_memory, orchestration, main, requirements_agent,
               architecture_agent, coder_agent, test_writer_agent, executor_agent,
               self_healing_agent, verifier_agent, doc_agent, project_details)
    for module in modules:
        for name in ("CONTRACT_FILE", "PLAN_FILE", "VERIFICATION_FILE", "ERRORS_FILE",
                     "FIXES_FILE", "OUTPUT_FILE", "PROJECT_FILE", "SERPAPI_CACHE_FILE",
                     "SERPAPI_LOG_FILE", "DECISIONS_FILE", "PROJECT_DETAILS_CACHE_FILE",
                     "SETTINGS_FILE", "WORKSPACE_DIR", "MEMORY_DIR", "generate_json"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, getattr(module, name))
    monkeypatch.setattr(main, "orchestrator", main.orchestrator)
    monkeypatch.setattr(self_healing_agent.SelfHealingAgent, "execute",
                        self_healing_agent.SelfHealingAgent.execute)
    browser_demo_server.configure(tmp_path)
    await main.save_settings(main.SettingsRequest(generate_project_details=True,
                                                  skill_level="beginner"))
    assert (await main.get_settings())["generate_project_details"] is True
    pipeline = main.orchestrator
    await pipeline.start("Build me a Celsius to Fahrenheit CLI")
    for answer in ("Temperature converter", "Celsius number", "Fahrenheit number",
                   "Reject invalid input"):
        await pipeline.answer(answer)
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=30)
    await pipeline.approve(True)
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=45)
    assert pipeline.status()["phase"] == "complete"
    assert (await main.project_details_list())["files"] == [
        "level_1_summary.md", "level_2_paragraph.md"]
    assert "temperature conversion" in (await main.project_details_file(
        "level_1_summary.md"))["content"]

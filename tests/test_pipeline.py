# Exercise the approval pause, SerpApi repair, verification retry, and documentation.

import asyncio
from pathlib import Path

import pytest

from backend import main as api_main, orchestrator as orchestration
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

    async def fake_generate_json(system: str, user: str, **kwargs: object) -> dict:
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
            assert state["question"] == requirements_agent.questions_for_project(
                "Build me a Celsius to Fahrenheit CLI",
                ["A temperature converter", "A Celsius number", "A Fahrenheit number"][:index + 1],
            )[index + 1]
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
async def test_web_app_request_builds_previewable_interactive_prototype(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Web requirements produce browser assets, acceptance checks, preview, and usage docs."""
    memory = tmp_path / "memory"
    workspace = tmp_path / "workspace"
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
    modules = (shared_memory, orchestration, api_main, requirements_agent,
               architecture_agent, coder_agent, test_writer_agent, executor_agent,
               self_healing_agent, verifier_agent, doc_agent)
    for module in modules:
        for name, path in paths.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, path)
        if hasattr(module, "WORKSPACE_DIR"):
            monkeypatch.setattr(module, "WORKSPACE_DIR", workspace)

    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Reading Tracker</title><link rel="stylesheet" href="styles.css"></head>'
        '<body><main><h1>Reading Tracker</h1><form id="book-form">'
        '<label for="book-title">Book title</label><input id="book-title" required>'
        '<button type="submit">Add book</button></form><ul id="book-list"></ul>'
        '<p id="empty-state">Your list is ready.</p></main>'
        '<script defer src="app.js"></script></body></html>'
    )
    css = ("body { margin: 0; font-family: Georgia, serif; background: #f8f5ef; }\n"
           "main { max-width: 48rem; margin: 3rem auto; padding: 1rem; }\n"
           "button { min-height: 44px; }\n")
    js = (
        'const bookForm = document.querySelector("#book-form");\n'
        'const bookList = document.querySelector("#book-list");\n'
        'function addBook(event) { event.preventDefault(); const title = document.querySelector("#book-title").value.trim(); '
        'if (!title) return; const item = document.createElement("li"); item.textContent = title; '
        'const done = document.createElement("button"); done.type = "button"; done.textContent = "Mark finished"; '
        'item.append(done); bookList.append(item); bookForm.reset(); }\n'
        'bookForm.addEventListener("submit", addBook);\n'
        'bookList.addEventListener("click", (event) => { if (event.target.matches("button")) '
        'event.target.closest("li").classList.toggle("finished"); });\n'
    )
    web_tests = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).parent\n"
        "HTML = (ROOT / 'index.html').read_text(encoding='utf-8')\n"
        "JS = (ROOT / 'app.js').read_text(encoding='utf-8')\n"
        "# Acceptance: Add a book to the reading list\n"
        "def test_add_a_book():\n"
        "    assert 'id=\"book-form\"' in HTML\n"
        "    assert 'bookForm.addEventListener(\"submit\", addBook)' in JS\n"
        "# Acceptance: Mark a book as finished\n"
        "def test_mark_a_book_finished():\n"
        "    assert 'Mark finished' in JS\n"
        "    assert 'classList.toggle(\"finished\")' in JS\n"
    )
    calls: list[str] = []

    async def generate(system: str, user: str, **kwargs: object) -> dict:
        """Supply a small project that follows the same agent schemas as live generation."""
        calls.append(system)
        index = len(calls)
        if index == 1:
            return {"app_name": "Reading Tracker", "description": "A warm reading tracker for books in progress.",
                    "project_type": "web_app", "design_direction": "Warm editorial, quiet color palette.",
                    "inputs": ["Book title"], "outputs": ["Reading list and completion state"],
                    "edge_cases": ["Reject blank titles", "Show an empty state"]}
        if index == 2:
            return {"project_type": "web_app", "tech_stack": {"language": "html_css_javascript", "libraries": []},
                    "file_structure": [
                        {"path": "index.html", "purpose": "Accessible reading tracker page", "depends_on": []},
                        {"path": "styles.css", "purpose": "Responsive editorial style", "depends_on": []},
                        {"path": "app.js", "purpose": "Add and complete reading items", "depends_on": ["index.html"]},
                        {"path": "test_main.py", "purpose": "Acceptance tests for requested flows", "depends_on": ["index.html", "app.js"]},
                    ],
                    "build_order": ["index.html", "styles.css", "app.js", "test_main.py"],
                    "acceptance_criteria": [
                        {"feature": "Add a book to the reading list", "given": "A title is entered", "when": "The form is submitted", "then": "The new book appears in the list"},
                        {"feature": "Mark a book as finished", "given": "A book is listed", "when": "Mark finished is clicked", "then": "The item changes to finished"},
                    ], "risks": []}
        if index == 3:
            return {"index.html": html, "styles.css": css, "app.js": js}
        if index == 4:
            return {"test_main.py": web_tests}
        if index == 5:
            return {"features": [
                {"feature": "Add a book to the reading list", "status": "pass",
                 "evidence": 'bookForm.addEventListener("submit", addBook)'},
                {"feature": "Mark a book as finished", "status": "pass",
                 "evidence": 'classList.toggle("finished")'},
            ]}
        raise AssertionError(f"Unexpected generation call {index}: {system[:80]}")

    for module in (requirements_agent, architecture_agent, coder_agent,
                   test_writer_agent, verifier_agent):
        monkeypatch.setattr(module, "generate_json", generate)
    pipeline = orchestration.Orchestrator()
    state = await pipeline.start("Build a browser-based reading tracker app")
    assert state["question"] == requirements_agent.QUESTIONS[0]
    answers = ["A browser-based web app", "Add books and mark them finished.",
               "For readers; warm editorial colors and clear typography.",
               "Reject blank titles and show an empty list."]
    for index, answer in enumerate(answers):
        state = await pipeline.answer(answer)
        if index == 0:
            assert "screens and actions" in state["question"]
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=15)
    assert pipeline.status()["phase"] == "awaiting_approval"
    assert shared_memory.read_json(paths["CONTRACT_FILE"])["project_type"] == "web_app"
    assert shared_memory.read_json(paths["PLAN_FILE"])["tech_stack"]["language"] == "html_css_javascript"
    await pipeline.approve(True)
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=30)
    assert pipeline.status()["phase"] == "complete", {
        "state": pipeline.status(), "output": shared_memory.read_json(paths["OUTPUT_FILE"]),
        "errors": shared_memory.read_json(paths["ERRORS_FILE"], []),
    }
    project = workspace / "reading_tracker"
    assert {"index.html", "styles.css", "app.js", "test_main.py", "README.md"}.issubset(
        {item.name for item in project.iterdir()})
    assert shared_memory.read_json(paths["OUTPUT_FILE"])["success"] is True
    assert shared_memory.read_json(paths["VERIFICATION_FILE"])["layers"][0]["status"] == "pass"
    assert "Browser prototype" in (project / "README.md").read_text(encoding="utf-8")
    api_files = await api_main.project_files()
    assert "Preview" in api_files["files"]
    preview_response = await api_main.project_preview()
    preview = preview_response.body.decode("utf-8")
    assert "<style>" in preview and "font-family: Georgia" in preview
    assert '<script>' in preview and "bookForm.addEventListener" in preview
    assert "devsprint-preview-storage-ready" in preview
    assert "devsprint-preview-storage-init" in preview
    assert "script.textContent" in preview
    assert "connect-src 'none'" in preview_response.headers["content-security-policy"]
    viewer_markup = (api_main.ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'sandbox="allow-scripts allow-modals"' in viewer_markup
    assert "allow-same-origin" not in viewer_markup


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


@pytest.mark.asyncio
@pytest.mark.parametrize("saved_phase,saved_agent,expected_calls", [
    ("building", "Test Writer", ["test_writer", "executor", "verifier", "doc"]),
    ("building", "Executor", ["executor", "verifier", "doc"]),
    ("building", "Self-Healing", ["test_writer", "executor", "verifier", "doc"]),
    ("error", "Executor", ["test_writer", "executor", "verifier", "doc"]),
    ("error", "Coder", ["executor", "verifier", "doc"]),
])
async def test_resume_interrupted_test_writer_preserves_generated_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    saved_phase: str, saved_agent: str, expected_calls: list[str],
) -> None:
    """A server restart resumes from saved files without regenerating approved code."""
    memory = tmp_path / "memory"
    workspace = tmp_path / "workspace"
    memory.mkdir()
    project = workspace / "calculator"
    project.mkdir(parents=True)
    (project / "main.py").write_text("print('approved code')\n", encoding="utf-8")
    test_content = ("# Deterministic fallback: source-level smoke checks, not browser behavior tests.\n"
                    "from pathlib import Path\n"
                    "def test_saved(): assert Path(__file__).with_name('main.py').is_file()\n" if saved_agent == "Self-Healing" else
                    "from pathlib import Path\n"
                    "def test_saved(): assert Path(__file__).with_name('main.py').is_file()\n")
    (project / "test_main.py").write_text(test_content, encoding="utf-8")
    paths = {name: memory / filename for name, filename in {
        "PROJECT_FILE": "project.json", "CONTRACT_FILE": "contract.json",
        "PLAN_FILE": "plan.json", "VERIFICATION_FILE": "verification.json",
        "OUTPUT_FILE": "output.json",
    }.items()}
    for name, path in paths.items():
        monkeypatch.setattr(orchestration, name, path)
        monkeypatch.setattr(shared_memory, name, path)
    monkeypatch.setattr(orchestration, "WORKSPACE_DIR", workspace)
    shared_memory.write_json(paths["PROJECT_FILE"], {
        "phase": saved_phase, "agent": saved_agent, "approved": True,
        "verification_retry": 0, "completed_agents": ["Coder"],
    })
    shared_memory.write_json(paths["CONTRACT_FILE"], {"project_name": "calculator"})
    shared_memory.write_json(paths["PLAN_FILE"], {"acceptance_criteria": [{"feature": "Add"}]})
    if saved_phase == "error" and saved_agent == "Coder":
        shared_memory.write_json(paths["OUTPUT_FILE"], {"success": True})
    pipeline = orchestration.Orchestrator()
    assert pipeline.status()["is_running"] is False
    calls: list[str] = []

    async def coded(context: dict, message: str = "") -> dict:
        """Catch an unintended source regeneration."""
        calls.append("coder")
        return {}

    async def tested(context: dict, message: str = "") -> dict:
        """Stand in for completed acceptance tests."""
        calls.append("test_writer")
        return {}

    async def executed(context: dict, message: str = "") -> dict:
        """Stand in for a successful subprocess run."""
        calls.append("executor")
        return {"success": True}

    async def verified(context: dict, message: str = "") -> dict:
        """Return a complete verification report."""
        calls.append("verifier")
        return {"gaps": [], "report": {"gaps": []}}

    async def documented(context: dict, message: str = "") -> dict:
        """Stand in for project documentation."""
        calls.append("doc")
        return {}

    for agent, fake in ((pipeline.coder, coded), (pipeline.test_writer, tested),
                        (pipeline.executor, executed), (pipeline.verifier, verified),
                        (pipeline.doc, documented)):
        monkeypatch.setattr(agent, "execute", fake)
    await pipeline.resume()
    assert pipeline._task is not None
    await asyncio.wait_for(pipeline._task, timeout=5)
    assert calls == expected_calls
    assert (project / "main.py").read_text(encoding="utf-8") == "print('approved code')\n"
    assert pipeline.status()["phase"] == "complete"

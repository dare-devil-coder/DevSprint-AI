# Serve a fully mocked DevSprint workflow for browser verification without API keys.
"""Run the real FastAPI UI with deterministic local agent responses."""

from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from backend import main, orchestrator as orchestration
from backend.agents import (
    architecture_agent, coder_agent, doc_agent, executor_agent, requirements_agent,
    self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.memory import shared_memory


def configure(root: Path) -> None:
    """Redirect all workflow files and substitute model and search responses."""
    memory = root / "memory"
    workspace = root / "workspace"
    memory.mkdir()
    workspace.mkdir()
    paths = {name: memory / filename for name, filename in {
        "CONTRACT_FILE": "contract.json", "PLAN_FILE": "plan.json",
        "VERIFICATION_FILE": "verification.json", "ERRORS_FILE": "errors.json",
        "FIXES_FILE": "fixes.json", "OUTPUT_FILE": "output.json",
        "PROJECT_FILE": "project.json", "SERPAPI_CACHE_FILE": "serpapi_cache.json",
        "SERPAPI_LOG_FILE": "serpapi_log.json",
    }.items()}
    for module in (shared_memory, orchestration, main, requirements_agent,
                   architecture_agent, coder_agent, test_writer_agent, executor_agent,
                   self_healing_agent, verifier_agent, doc_agent):
        for name, path in paths.items():
            if hasattr(module, name):
                setattr(module, name, path)
        if hasattr(module, "WORKSPACE_DIR"):
            setattr(module, "WORKSPACE_DIR", workspace)

    counts = {"coder": 0, "verifier": 0}

    async def generate(system: str, user: str) -> dict:
        """Return product-shaped artifacts for the active agent prompt."""
        if "app_name" in system and "edge_cases" in system:
            return {"app_name": "Temperature CLI", "description": "Convert Celsius to Fahrenheit",
                    "inputs": ["Celsius number"], "outputs": ["Fahrenheit number"],
                    "edge_cases": ["Invalid input"]}
        if "file_structure" in system:
            return {"tech_stack": {"language": "python", "libraries": ["pytest"]},
                    "file_structure": [
                        {"path": "main.py", "purpose": "Convert values", "depends_on": []},
                        {"path": "test_main.py", "purpose": "Test conversion", "depends_on": ["main.py"]},
                    ], "build_order": ["main.py", "test_main.py"],
                    "acceptance_criteria": [{"feature": "Freezing conversion",
                                             "given": "zero Celsius", "when": "converted",
                                             "then": "returns 32 Fahrenheit"}], "risks": []}
        if "test_main.py as the full pytest source" in system:
            return {"test_main.py": "from main import convert\n\n# Acceptance: Freezing conversion\n"
                                    "def test_freezing_conversion():\n    assert convert(0) == 32\n"}
        if "features array" in system:
            counts["verifier"] += 1
            return {"features": [{"feature": "Freezing conversion", "status": "pass",
                                  "evidence": "return c * 9 / 5 + 32"}]}
        if "main.py" in system:
            counts["coder"] += 1
            return {"main.py": "def convert(c):\n    return c * 9 / 5 + 32\n\n"
                               "if __name__ == '__main__':\n    print(convert(0))\n",
                    "test_main.py": "def test_placeholder():\n    assert True\n"}
        raise ValueError("Unexpected demo model request")

    for module in (requirements_agent, architecture_agent, coder_agent,
                   test_writer_agent, self_healing_agent, verifier_agent):
        module.generate_json = generate

    async def no_search(context: dict, message: str = "") -> dict:
        """Avoid external SerpApi calls in the browser demonstration."""
        return {"fixed": True}

    self_healing_agent.SelfHealingAgent.execute = no_search
    main.orchestrator = orchestration.Orchestrator()


if __name__ == "__main__":
    with TemporaryDirectory(prefix="devsprint-browser-") as location:
        configure(Path(location))
        uvicorn.run(main.app, host="127.0.0.1", port=8000, log_level="warning")

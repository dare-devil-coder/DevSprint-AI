# Serve a fully mocked DevSprint workflow for browser verification without API keys.
"""Run the real FastAPI UI with deterministic local agent responses."""

import os
from pathlib import Path

import uvicorn

from backend import main, orchestrator as orchestration, serpapi_client
from backend.agents import (
    architecture_agent, coder_agent, doc_agent, executor_agent, requirements_agent,
    self_healing_agent, test_writer_agent, verifier_agent,
)
from backend.memory import project_details, shared_memory


def configure(root: Path) -> None:
    """Redirect all workflow files and substitute model and search responses."""
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
    for module in (shared_memory, orchestration, main, serpapi_client, requirements_agent,
                   architecture_agent, coder_agent, test_writer_agent, executor_agent,
                   self_healing_agent, verifier_agent, doc_agent, project_details):
        for name, path in paths.items():
            if hasattr(module, name):
                setattr(module, name, path)
        if hasattr(module, "WORKSPACE_DIR"):
            setattr(module, "WORKSPACE_DIR", workspace)
        if hasattr(module, "MEMORY_DIR"):
            setattr(module, "MEMORY_DIR", memory)

    counts = {"coder": 0, "verifier": 0}

    def cli_source(formula: str) -> str:
        """Build the same runnable CLI with either a broken or correct formula."""
        return (
            "# Convert a Celsius command line argument to Fahrenheit.\n"
            "import argparse\n\n"
            f"def convert(c: float) -> float:\n    return {formula}\n\n"
            "def main() -> None:\n"
            "    parser = argparse.ArgumentParser(description='Convert Celsius to Fahrenheit')\n"
            "    parser.add_argument('celsius', type=float)\n"
            "    args = parser.parse_args()\n"
            "    print(convert(args.celsius))\n\n"
            "if __name__ == '__main__':\n    main()\n"
        )

    async def generate(system: str, user: str, **kwargs: object) -> dict:
        """Return product-shaped artifacts for the active agent prompt."""
        if "app_name" in system and "edge_cases" in system:
            counts["coder"] = 0
            counts["verifier"] = 0
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
            return {"test_main.py": (
                "# Check CLI conversion and invalid input.\n"
                "import subprocess\nimport sys\nfrom pathlib import Path\nfrom main import convert\n\n"
                "# Acceptance: Freezing conversion\n"
                "def test_freezing_conversion():\n    assert convert(0) == 32\n\n"
                "def test_boiling_conversion():\n    assert convert(100) == 212\n\n"
                "def test_invalid_input():\n"
                "    result = subprocess.run([sys.executable, "
                "str(Path(__file__).with_name('main.py')), 'abc'], "
                "capture_output=True, text=True, check=False)\n"
                "    assert result.returncode != 0\n"
                "    assert 'invalid float value' in result.stderr\n"
            )}
        if "features array" in system:
            counts["verifier"] += 1
            return {"features": [{"feature": "Freezing conversion", "status": "pass",
                                  "evidence": "return c * 9 / 5 + 32"}]}
        if "Repair the reported failure" in system:
            import json

            current = json.loads(user)["current_code"]
            return {"main.py": cli_source("c * 9 / 5 + 32"),
                    "test_main.py": current["test_main.py"]}
        if "main.py" in system:
            counts["coder"] += 1
            formula = "c * 9 / 5" if counts["coder"] == 1 else "c * 9 / 5 + 32"
            return {"main.py": cli_source(formula),
                    "test_main.py": "def test_placeholder():\n    assert True\n"}
        raise ValueError("Unexpected demo model request")

    for module in (requirements_agent, architecture_agent, coder_agent,
                   test_writer_agent, self_healing_agent, verifier_agent):
        module.generate_json = generate

    async def explain(system: str, user: str, model: str | None = None,
                      capability: str | None = None) -> dict[str, str]:
        """Return deterministic explanations while preserving cheap-model routing."""
        if "one key, explanation" not in system:
            raise ValueError("Unexpected Project Details model request")
        if "exactly one useful sentence" in system:
            return {"explanation": "This file supports the approved temperature conversion project."}
        if "one concise paragraph" in system:
            return {"explanation": "This file implements or explains the temperature converter, working with the other generated files to meet the approved conversion criterion."}
        if "connects to the other" in system:
            return {"explanation": "This file connects the conversion behavior, acceptance test, and usage instructions."}
        return {"explanation": "The file's functions implement conversion and the tests check the freezing point."}

    project_details.generate_json = explain

    import serpapi

    def fixture_search(self: object, params: dict) -> dict:
        """Return a labeled search fixture while exercising the real logging path."""
        return {"organic_results": [{
            "title": "[MOCK] Celsius to Fahrenheit formula",
            "snippet": "Fahrenheit = Celsius * 9 / 5 + 32.",
            "link": "https://example.test/temperature-formula",
        }]}

    os.environ["SERPAPI_API_KEY"] = "browser-test-fixture"
    serpapi.Client.search = fixture_search
    main.orchestrator = orchestration.Orchestrator()


if __name__ == "__main__":
    location = Path(os.getenv("DEMO_DATA_DIR", "demo_evidence/runtime"))
    configure(location)
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.getenv("DEMO_PORT", "8001")), log_level="warning")

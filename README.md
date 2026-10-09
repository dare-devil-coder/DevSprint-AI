<!-- Setup, workflow, and verification for DevSprint AI Phase 2. -->
# DevSprint AI

DevSprint AI turns a small Python CLI idea into a reviewed plan, source code, tests, and a project README. It asks four clarification questions, creates a contract and architecture plan, and **pauses for explicit approval** before generating code.

## Run

1. Use Python 3.10 or newer.
2. Create a virtual environment and install dependencies: `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` and set your own `OPENAI_API_KEY` and `SERPAPI_API_KEY`. Keep `.env` private.
4. From the project root, run `python -m uvicorn backend.main:app --reload`.
5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The frontend is HTML, CSS, and vanilla JavaScript. Mermaid is loaded from a CDN for architecture diagrams. The backend uses FastAPI. Generated projects are saved under `workspace/`; contracts, plans, execution results, verifier reports, errors, fixes, cache entries, and the SerpApi audit trail are JSON files under `memory/`.

## Workflow

1. Requirements turns the four answers into `contract.json`.
2. Architecture produces `plan.json` with a Python stack, exactly `main.py` and `test_main.py`, build order, and acceptance criteria.
3. The approval modal shows both artifacts. **Edit Contract** saves changes and regenerates the plan. **Approve & Build** is the only action that starts coding.
4. Coder writes the CLI. Test Writer replaces its initial tests with pytest checks mapped to the approved criteria.
5. Executor runs the CLI and tests. On failure, Self-Healing uses SerpApi results to repair them, with at most five repair attempts. Search calls and cache hits appear in the SerpApi Log.
6. Verifier writes `verification.json` with six layer statuses and per-feature evidence. Gaps return to Coder for at most three revisions.
7. Doc Agent writes the generated project's `README.md` after verification passes.

The viewer exposes the contract, plan, source, tests, README, output, verification report, and SerpApi log. Archify shows user workflow, system architecture, and data flow diagrams derived from the contract and plan.

## Verify

Run `python -m pytest -q tests`. The suite mocks model and search calls, covering the approval pause, contract and plan validation, generated acceptance tests, execution repair, verifier evidence, the three-revision limit, and documentation.

For local browser verification without API keys, run `python -m tests.browser_demo_server`. It serves the real UI on port 8000 with isolated temporary project data and deterministic agent responses. Stop that server before starting the normal app.

A real OpenAI and SerpApi run requires valid keys and network access. Generated code runs as a local subprocess with a timeout. This is a hackathon execution boundary, not a security sandbox for untrusted code; run the app only where generated code is safe to execute.

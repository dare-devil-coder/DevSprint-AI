<!-- Setup, workflow, and verification for DevSprint AI. -->
# DevSprint AI

DevSprint AI turns a plain-language idea into a reviewed Python CLI or responsive browser prototype. It asks format-specific clarification questions, creates a contract and architecture plan, and **pauses for explicit approval** before generating code. Web projects include an interactive HTML/CSS/JavaScript prototype and an in-app preview; CLI projects keep their Python workflow. Phase 3 adds scoped agent memory, task matched skills, optional learner explanations, and a clean demo setup.

## Run

1. Use Python 3.10 or newer.
2. Create a virtual environment and install dependencies: `python -m pip install -r requirements.txt`.
3. Copy `.env.example` to `.env`, set `SERPAPI_API_KEY`, and configure at least one of `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `NVIDIA_API_KEY`, or `GEMINI_API_KEY`. `OPENAI_API_KEY` remains an optional legacy fallback. Keep `.env` private.
4. From the project root, run `python -m uvicorn backend.main:app`. Keep this server running while the agents build. Auto reload can restart the worker when generated Python files change and interrupt the pipeline.
5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The frontend is HTML, CSS, and vanilla JavaScript. Mermaid is loaded from a CDN for architecture diagrams. The backend uses FastAPI. Generated projects are saved under `workspace/`; contracts, plans, execution results, verifier reports, errors, fixes, decisions, settings, cache entries, and the SerpApi audit trail are JSON files under `memory/`.

If a prior `--reload` run stopped during a build, restart with the command above and send `POST /api/project/resume` to continue from the saved source and tests. The app preserves the contract and plan.

## Workflow

1. Requirements asks which format to build, then tailors follow-up questions for the requested interface or CLI workflow. The answers become `contract.json`.
2. Architecture produces a type-specific `plan.json` and acceptance criteria. Browser prototypes use `index.html`, `styles.css`, and `app.js`; CLI projects use `main.py` and `test_main.py`.
3. The approval modal shows both artifacts. **Edit Contract** saves changes and regenerates the plan. **Approve & Build** is the only action that starts coding.
4. Coder builds the requested interface or CLI. Test Writer creates pytest checks mapped to the approved criteria.
5. Executor runs the CLI or validates the prototype assets and tests. On failure, Self-Healing uses SerpApi results to repair them, with at most five repair attempts. Search calls and cache hits appear in the SerpApi Log.
6. Verifier writes `verification.json` with six layer statuses and per-feature evidence. Gaps return to Coder for at most three revisions.
7. Doc Agent writes the generated project's `README.md` after verification passes.

The viewer exposes the live browser preview when available, plus the contract, plan, source, tests, README, output, verification report, and SerpApi log. Archify shows user workflow, system architecture, and data flow diagrams derived from the contract and plan.

## Settings and learner explanations

Open **Settings** to choose a beginner, intermediate, or advanced explanation level and optionally enable **Generate Project Details folder**. The toggle is off by default. The choice is saved by the backend and mirrored in browser local storage. When enabled before a build, the app writes `level_1_summary.md` and `level_2_paragraph.md` in the generated project's `project_details/` folder. Open **Project Details** in the viewer to read them. **Explain deeper** generates level 3, then level 4, only when requested. The first two levels use the low-cost model route (or `OPENAI_MODEL_CHEAP` if OpenAI is explicitly configured) and explanations are cached by source hash.

## Model routing and fallback

Each agent declares the capability it needs. The shared client tries configured models in the order in [MODEL_ROUTING.md](docs/MODEL_ROUTING.md). A failed request, rate limit, timeout, empty response, or malformed JSON moves to the next provider automatically. Failed providers enter a short cooldown, and the server logs provider and model names without logging keys or prompt contents. The Doc Agent and Executor do not need an LLM call. SerpApi remains separate and is called only by Self-Healing when execution fails.

Check the configured key catalogs with `python -m scripts.probe_models`, make small live JSON probes with `python -m scripts.probe_models --live`, or verify the actual router with `python -m scripts.probe_models --router`. `--coding-smoke` checks that the chosen coding model returns two parseable Python files without executing them. `--serpapi` checks the search key through the existing client with an isolated temporary log. Use the project `.venv` for these commands after installing dependencies. Live checks may consume provider quota.

## Skills and memory

Each agent receives only the contract fields, allowed files, and the two most recent errors and fixes relevant to its task. Decisions are recorded in `memory/decisions.json` with feature, file, agent, and timestamp tags. The three bundled skills are Python best practices, testing patterns, and error handling. The app loads their short metadata first; an agent receives full instructions only when a trigger matches its current task. Active skills appear above the timeline.

## Demo Mode

**Demo Mode** opens a confirmation dialog. Confirming clears this local app's generated memory and workspace and prefills a Celsius to Fahrenheit CLI idea. Submit it, answer the four questions, inspect and approve the plan, then watch the build. This requires at least one working LLM provider; SerpApi is used only if execution fails and the repair loop starts. The SerpApi Log tab distinguishes live searches from cache hits. The reset removes prior generated projects and audit records, so export anything you need before using it. See [demo script](docs/DEMO_SCRIPT.md) for the recording sequence.

## Token efficiency

The contract and architecture are generated once and reused. Scoped memory limits each agent's context to relevant contract fields, allowlisted files, and the two latest errors and fixes. Skill metadata stays cheap until a trigger loads an instruction body. Levels 1 and 2 of Project Details use the cheaper model; levels 3 and 4 are deferred until requested. File-hash caching avoids regenerating unchanged explanations, and SerpApi caches queries by hash.

## Verify

Run `python -m pytest -q tests`. The suite mocks model and search calls, covering the approval pause, contract and plan validation, generated acceptance tests, execution repair, verifier evidence, the three-revision limit, documentation, and Phase 3 behavior.

For local browser verification without API keys, run `python -m tests.browser_demo_server`. It serves the real UI on port 8001 with project data under `demo_evidence/runtime/` and deterministic model and search fixtures. In another terminal, run `python -m tests.browser_e2e --base-url http://127.0.0.1:8001 --log-path demo_evidence/runtime/memory/serpapi_log.json --mode mocked --reset-isolated`. This deliberately makes the first generated conversion fail, then verifies the SerpApi logging and repair path, approval, final verification, and screenshots. Install Playwright and Chromium first with `python -m pip install playwright` and `python -m playwright install chromium`. Stop the demo server before starting the normal app.

The latest [browser result](demo_evidence/RESULT.md) is a **live-provider run**: 13/13 browser checks passed, three SerpApi lookups returned results, and the generated CLI passed six tests. The run used `python -m tests.browser_live_server` on port 8002 with isolated data under `demo_evidence/live_runtime/`. That test launcher deliberately inserted one missing import into the first generated file so the real Self-Healing path would execute. Run the browser script with `--base-url http://127.0.0.1:8002 --log-path demo_evidence/live_runtime/memory/serpapi_log.json --mode live --reset-isolated` to repeat it. [Approval](demo_evidence/01_approval_modal.png), [completed pipeline](demo_evidence/02_pipeline_complete.png), [verification](demo_evidence/03_verification.png), [SerpApi log](demo_evidence/04_serpapi_log.png), [390px](demo_evidence/05_mobile_390.png), [320px](demo_evidence/06_mobile_320.png), the [live log JSON](demo_evidence/live/serpapi_log.json), and the [generated CLI and tests](demo_evidence/live_project/) are saved for review. The separate [mocked result](demo_evidence/mocked/RESULT.md) verifies the same UI path without external API usage. The existing root `memory/serpapi_log.json` was preserved; the live test's new log is the exported evidence file.

A real LLM and SerpApi run requires valid keys and network access. Generated code runs as a local subprocess with a timeout. This is a hackathon execution boundary, not a security sandbox for untrusted code; run the app only where generated code is safe to execute.

<!-- Submission copy grounded in the implemented DevSprint AI workflow. -->
# Hackathon submission — DevSprint AI

## Track and summary

**Track:** AI Agents

**Project:** DevSprint AI

**One-line description:** A contract-driven agent workflow that plans, builds, tests, repairs, and verifies a small Python CLI project, using SerpApi to research execution failures.

DevSprint AI asks four clarification questions, writes a project contract and architecture plan, and pauses for user approval. Once approved, it generates source and acceptance tests, executes them, attempts one bounded repair if needed, verifies feature coverage, and writes a project README. Phase 3 adds scoped JSON memory, task-matched skills, optional learner explanations, a settings panel, and a clean demo setup.

## SerpApi integration

SerpApi is called from the Self-Healing path after an execution failure. The failing error is condensed into a search query, and the top three organic result snippets can inform the repair prompt. The client caches results by query hash, retries a 429 once after two seconds, and records the query, result count, cache status, timestamp, and error in `memory/serpapi_log.json`. A successful first build does not call SerpApi. A log entry with an error or `cached: true` does not demonstrate a new live search.

## Stack and scope

- Frontend: HTML, CSS, vanilla JavaScript, WebSocket; Mermaid loaded from a CDN for diagrams.
- Backend: Python, FastAPI, capability-routed OpenRouter/Groq/NVIDIA/Gemini models, SerpApi, JSON file memory.
- Output: one Python CLI project with `main.py`, `test_main.py`, README, verification evidence, and optional Project Details.
- Execution: local Python subprocess with a timeout. This is a hackathon execution boundary, not an isolation guarantee for untrusted code.

## Links and participant information

- Repository: https://github.com/dare-devil-coder/DevSprint-AI
- Demo video and lead participant contact details must be supplied by the team in the submission form. They are not stored in this repository.

## Reproduce

1. Install Python 3.10 or newer and run `python -m pip install -r requirements.txt`.
2. Copy `.env.example` to `.env`, then add `SERPAPI_API_KEY` and at least one supported LLM provider key. See `docs/MODEL_ROUTING.md` for the tested order.
3. Run `python -m uvicorn backend.main:app` and open `http://127.0.0.1:8000`.
4. Follow [the demo script](DEMO_SCRIPT.md). For a local UI walkthrough without API keys, run `python -m tests.browser_demo_server`; this uses mocked model and search responses and cannot establish live service usage.

## Evidence checklist for the team

- Record a complete build and verification report.
- Show Settings and optional Project Details levels 1 and 2, then generate level 3 on demand.
- Capture one actual Self-Healing cycle with a successful uncached SerpApi call and visible follow-up execution.
- Add the public demo video and participant details in the hackathon submission form.

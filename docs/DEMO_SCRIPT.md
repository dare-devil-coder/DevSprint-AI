<!-- Recording guide for the Phase 3 DevSprint AI workflow. -->
# DevSprint AI demo script

Target length: 3–5 minutes. Rehearse the complete run with your own API keys before recording. The local browser demo server uses mocks and does not prove a live LLM or SerpApi call.

## Before recording

1. Install dependencies and set `SERPAPI_API_KEY` plus at least one working LLM provider key in a private `.env` file. Run `python -m scripts.probe_models --router` to confirm the model routes before recording.
2. Start `python -m uvicorn backend.main:app` and open `http://127.0.0.1:8000`.
3. Confirm no project build is running. Use **Demo Mode**, read the reset notice, and confirm. This clears local generated projects, memory, cache, and the SerpApi log. The sample Celsius to Fahrenheit idea is filled in.
4. Open **Settings**, enable **Generate Project Details folder**, choose **Beginner**, and save.
5. Keep the SerpApi Log tab visible at the repair point if the generated first attempt fails. A successful first run will have no SerpApi call; do not claim otherwise. To show a real repair, rehearse a run that genuinely reaches Self-Healing with a valid key and network access.

## Scene 1 — The idea (0:00–0:35)

Show the three-panel workspace and submit the sample idea. Say: “DevSprint AI begins with a short brief and asks one question at a time before it writes code.”

## Scene 2 — Contract and plan (0:35–1:20)

Answer the four questions. Show the Requirements and Architecture steps, the active skill badges, the contract, and the three Archify diagrams. Point out that coding is paused until **Approve & Build**. Make a small contract edit if it helps the story; save it and show the regenerated plan. Then approve.

## Scene 3 — Build and repair (1:20–2:45)

Show Coder, Test Writer, Executor, Verifier, and Doc Agent in the timeline. Point to `python_best_practices` when Coder runs and `testing_patterns` when Test Writer runs. If execution fails, show Self-Healing, the SerpApi Log tab, the query and result count, and the subsequent run. Distinguish a live search (`cached: false`, no error) from a cache hit. If execution succeeds first time, say that the repair path was not needed on this run.

## Scene 4 — Verification and learning (2:45–3:45)

Show the verification report and its evidence for the approved criteria. Open the generated README. Open **Project Details** and show level 1 and level 2. Click **Explain deeper** to generate level 3; click again for level 4 only if time allows. Explain that deeper explanations are generated on request and cached for unchanged files.

## Scene 5 — Finish (3:45–4:15)

Show the saved project folder and the final timeline. Say: “The result is a reviewed plan, runnable code, tests, verification evidence, and optional explanations for learners.”

## Proof to capture separately

- A completed build and its verification report.
- The generated `project_details/` folder when the toggle was on.
- `memory/serpapi_log.json` with at least one successful, uncached call from an actual Self-Healing run. A mocked run or a logged error is not proof of a live SerpApi search.
- The public demo video URL and participant details, supplied by the team before submission.

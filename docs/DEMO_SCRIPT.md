
---

## Document 5 — `docs/DEMO_SCRIPT.md`

```markdown
# DevSprint AI — Demo Video Script

## Total Length
3 to 5 minutes.

## Pre-Recording Checklist
  - .env has SERPAPI_API_KEY and OPENAI_API_KEY
  - Backend running: uvicorn backend.main:app --reload
  - Frontend opened in browser (http://localhost:8000)
  - memory/serpapi_log.json is empty or cleared
  - Screen recorder ready, microphone tested

## Scene 1 — Problem (0:00 to 0:30)
SAY:
  "Most AI code tools write code and hand it to you. If it's broken, that's
   your problem. DevSprint AI is different. It asks what you want, writes a
   contract, builds the code, runs it, fixes it, and verifies it matches your
   request. And it uses SerpApi to search for real fixes when code fails."

SHOW: Landing page of DevSprint AI.

## Scene 2 — Clarification (0:30 to 1:15)
TYPE: "Build me a CLI tool that converts Celsius to Fahrenheit"

SHOW: Agent asks one question at a time. Answer 3 to 4 questions.

SAY:
  "Notice the agent asks one question at a time, like a human would. It
   doesn't dump a form on the user."

SHOW: Contract is displayed. Click "Approve & Build".

## Scene 3 — Build Loop (1:15 to 2:30)
SHOW: Agent timeline animating in the center panel.
  Requirements Agent  -> green check
  Architecture Agent  -> green check
  Coder Agent         -> green check
  Test Writer Agent   -> green check
  Executor Agent      -> red X (FAIL)

SAY:
  "The first attempt failed. Now watch the Self-Healing Agent."

SHOW: Self-Healing Agent working. Open memory/serpapi_log.json in a side window.

SAY:
  "The agent searched SerpApi for the exact error. This is what makes the fix
   fact-based instead of a guess."

SHOW: Executor Agent runs again -> green check (PASS).

## Scene 4 — Verification (2:30 to 3:15)
SHOW: Verification report panel.
  Frontend  -> verified
  Backend   -> verified
  Build     -> verified

SAY:
  "The Verifier Agent checks the built product against the original contract,
   layer by layer. Nothing passes until it matches what the user asked for."

## Scene 5 — Project Details (3:15 to 3:45)
SHOW: Toggle "Generate Project Details" ON. Show the generated explanation.

SAY:
  "For students and beginners, DevSprint AI can optionally generate a plain
   language explanation of the entire project — what each file does, why each
   choice was made."

## Scene 6 — Wrap-up (3:45 to 4:15)
SAY:
  "DevSprint AI is a contract-driven, self-healing multi-agent system.
   It understands what you want, builds it, tests it, fixes it with SerpApi,
   and verifies it matches your request. Not fast code — working code."

SHOW: Final project files in workspace/ and README.

## SerpApi Proof Shot
Show memory/serpapi_log.json with at least one logged call.
This is required for the hackathon.
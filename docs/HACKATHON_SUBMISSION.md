# Hackathon Submission — DevSprint AI

## Track
AI Agents

## Project Name
DevSprint AI

## One-Line Description
A contract-driven, self-healing multi-agent system that understands what you
want, builds it, tests it, fixes it with SerpApi, and verifies it matches your
request.

## Long Description
DevSprint AI is a multi-agent system that converts a plain-language idea into a
working, tested software project. Unlike existing code generators that hand you
code and leave you to debug it, DevSprint AI:

  1. Asks clarifying questions one at a time, like a human would.
  2. Produces a Project Contract — a formal, machine-readable specification.
  3. Plans the architecture before writing a single line of code.
  4. Writes code, tests, and runs everything in a sandbox.
  5. Self-heals: reads errors, searches SerpApi for current fixes, re-runs.
  6. Verifies the built product against the contract — frontend, backend,
     database, APIs, config, and build.
  7. Optionally generates a plain-language Project Details folder for learners.

## SerpApi Usage (Required Explanation)
SerpApi is used inside the self-healing loop. When generated code fails:

  1. The Executor Agent captures the error message.
  2. The Self-Healing Agent extracts the error type and library name.
  3. It calls SerpApi Google Search with a query like
     "python ModuleNotFoundError requests fix".
  4. The top 3 result snippets are passed to the LLM alongside the error and
     the failing code.
  5. The LLM produces a fix grounded in current, search-verified information
     instead of hallucinating an outdated API.

All SerpApi calls are logged to memory/serpapi_log.json as proof of usage.

## Tech Stack
  Frontend: HTML, CSS, vanilla JavaScript, WebSocket
  Backend:  Python 3.10+, FastAPI, uvicorn
  Search:   SerpApi (Google Search)
  LLM:      OpenAI
  Memory:   JSON files (no database)
  Sandbox:  Python subprocess

## Repository
<your GitHub URL>

## Demo Video
<your public video URL>

## Setup Instructions
  1. Clone the repository.
  2. cp .env.example .env
  3. Add SERPAPI_API_KEY and OPENAI_API_KEY to .env
  4. pip install -r requirements.txt
  5. uvicorn backend.main:app --reload
  6. Open http://localhost:8000

## Lead Participant
  Name: <your name>
  Email: <your email>
  Mobile: <your mobile>
  Occupation: <student / engineer / etc.>
  Years of experience: <number>
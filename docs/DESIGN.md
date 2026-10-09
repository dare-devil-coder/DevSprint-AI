# DevSprint AI — Design Document

## 1. Architecture Overview

FRONTEND (HTML / CSS / JS)
  - Chat Panel (questions and answers)
  - Agent Status Timeline (which agent is working)
  - Project Viewer (code, contract, output, verification)

        |
        | WebSocket + REST
        v

BACKEND (FastAPI)
  - Orchestrator (main pipeline loop)
  - Agents:
      1. Requirements Agent
      2. Architecture Agent
      3. Coder Agent
      4. Executor Agent
      5. Test Writer Agent
      6. Self-Healing Agent  (uses SerpApi)
      7. Verifier Agent
      8. Doc Agent
  - SerpApi Client (search_for_fix, search_for_docs)
  - Shared Memory (JSON files)

        |
        v

WORKSPACE (generated projects)

## 2. Agent Communication (Blackboard Pattern)
Agents do not talk to each other directly. They read from and write to shared
JSON files. This is a blackboard architecture — a shared whiteboard that every
agent reads before acting and writes to after finishing.

## 3. The Three Loops

LOOP 1: Clarification Loop (Requirements Agent <-> User)
  User idea -> Agent asks Q1 -> User answers -> Agent asks Q2 -> ...
  -> Agent produces contract.json -> USER APPROVES

LOOP 2: Build Loop (Coder -> Executor -> Self-Healing)
  Coder writes code -> Executor runs -> FAIL -> Self-Healing reads error
  -> SerpApi searches for fix -> Self-Healing fixes code -> Executor runs again
  -> Repeat until PASS (max 5 retries)

LOOP 3: Verification Loop (Verifier -> Coder)
  Verifier reads contract + built code -> checks each requirement
  -> If gap found -> sends back to Coder -> re-verify
  -> Only passes when 100% requirements met

## 4. Frontend Design (HTML/CSS/JS Only)

Layout: Three-panel design

  Left panel (30%)   — Chat interface.
                       Shows agent questions and user answers.
                       One question at a time. Clean, minimal design.

  Center panel (40%) — Agent Status Timeline.
                       Shows which agent is currently working.
                       Each agent has an icon, name, and status
                       (idle / working / done / error).
                       Animates as agents progress.

  Right panel (30%)  — Project Viewer.
                       Shows generated code files (tabs),
                       contract.json (pretty-printed),
                       execution output, and verification report.

Design System:
  Colors:    dark theme
             background: #0a0a0f
             panels:     #1a1a2e
             accent:     #00d4aa
  Font:      Inter or system font stack
  Cards:     subtle shadows
  Motion:    smooth CSS transitions (no JS animation library)
  Status:    pulsing dot for "working", green check for "done",
             red X for "error"
  Live:      WebSocket connection for real-time agent status updates

## 5. Backend Design (Python + FastAPI)

Endpoints:
  POST /api/project/start           start a new project with initial idea
  POST /api/project/answer          submit answer to a clarification question
  GET  /api/project/status          current agent status
  GET  /api/project/files           list generated files
  GET  /api/project/file/{path}     get file content
  WS   /ws/status                   real-time agent status stream
  GET  /api/verification/report     get verification results

Orchestrator:
  Runs the agent pipeline sequentially.
  Each agent is a Python class with a run(context) method.
  Context is loaded from shared memory.
  Status updates are broadcast via WebSocket.

## 6. SerpApi Integration Detail

Client setup:
  import serpapi
  import os
  client = serpapi.Client(api_key=os.getenv("SERPAPI_API_KEY"))

search_for_fix(error_message, language):
  query = f"{language} {error_message[:100]} fix"
  results = client.search({ "engine": "google", "q": query, "num": 3 })
  return top 3 organic results as { title, snippet, link }

search_for_docs(library, topic):
  query = f"{library} {topic} documentation"
  results = client.search({ "engine": "google", "q": query, "num": 2 })
  return top 2 snippets

## 7. File Structure

devsprint-ai/
  docs/
    PRD.md
    DESIGN.md
    AGENTS.md
    SERPAPI_USAGE.md
  backend/
    main.py                      FastAPI app entry point
    orchestrator.py              Pipeline coordinator
    websocket_manager.py         Real-time status broadcaster
    serpapi_client.py            SerpApi wrapper
    agents/
      __init__.py
      base_agent.py              Abstract base class
      requirements_agent.py      Agent 1: Asks questions
      architecture_agent.py      Agent 2: Plans system
      coder_agent.py             Agent 3: Writes code
      executor_agent.py          Agent 4: Runs code
      test_writer_agent.py       Agent 5: Writes tests
      self_healing_agent.py      Agent 6: Fixes errors (uses SerpApi)
      verifier_agent.py          Agent 7: Checks contract compliance
      doc_agent.py               Agent 8: Generates documentation
    memory/
      __init__.py
      shared_memory.py           JSON file read/write
      contract_schema.py         Contract dataclass
    models/
      __init__.py
      contract.py                ProjectContract model
      agent_status.py            AgentStatus enum
    utils/
      __init__.py
      sandbox.py                 Subprocess code execution
      logger.py                  Structured logging
  frontend/
    index.html                   Main UI
    css/
      style.css                  All styles
    js/
      app.js                     Main app logic
      websocket.js               WebSocket client
      chat.js                    Chat panel logic
      timeline.js                Agent status timeline
      viewer.js                  Code/output viewer
    assets/
      icons/                     Agent icons (SVG)
  workspace/                     Generated projects go here
  tests/
    test_agents.py
    test_serpapi.py
  .env.example                   SERPAPI_API_KEY, OPENAI_API_KEY
  requirements.txt
  README.md

## 8. Agent Status Flow (Frontend Display)

Each agent transitions through:
  IDLE -> WORKING -> DONE
  IDLE -> WORKING -> ERROR

Timeline example:
  1. Requirements Agent   pulsing blue -> green check
  2. Architecture Agent   pulsing blue -> green check
  3. Coder Agent          pulsing blue -> green check
  4. Test Writer Agent    pulsing blue -> green check
  5. Executor Agent       pulsing blue -> red X (attempt 1) -> yellow (retry)
  6. Self-Healing Agent   pulsing blue -> green check
  7. Executor Agent       pulsing blue -> green check (attempt 2)
  8. Verifier Agent       pulsing blue -> green check
  9. Doc Agent            pulsing blue -> green check
 10. PROJECT COMPLETE

Each status change is broadcast via WebSocket and animates on the frontend.

## 9. Token Efficiency Strategy
  1. Generate once, reuse everywhere: contract.json is generated once and read
     by all agents.
  2. Scope every retrieval: each agent gets only the contract section it needs.
  3. Use cheaper models for explanations: explanation is low-stakes.
  4. Cache reusable parts: common stacks have pre-written templates.
  5. SerpApi results are cached per error signature to avoid duplicate searches.
# AGENTS.md — Codex Instructions for DevSprint AI

## Project Overview
DevSprint AI is a multi-agent system that converts natural language ideas into
working, tested code. It uses SerpApi for real-time search during self-healing.

## Tech Stack
  Backend:  Python 3.10+, FastAPI, uvicorn, serpapi, python-dotenv, pydantic, openai
  Frontend: HTML5, CSS3, vanilla JavaScript (ES6+), WebSocket API
  LLM:      OpenRouter, Groq, NVIDIA, Gemini; optional OpenAI fallback
  No frameworks: No React, Vue, or Angular. Pure HTML/CSS/JS only.
  No ORM:   JSON files for memory. No database.

## Code Style
  Python:     PEP 8, type hints on all functions, docstrings on all classes and
              public methods.
  JavaScript: ES6+, const/let (never var), async/await, JSDoc comments on all
              functions.
  CSS:        BEM naming convention, CSS custom properties for colors.
  Every file must start with a comment explaining its purpose.

## File Rules
  - One agent per file in backend/agents/
  - Every agent extends BaseAgent and implements run(context) -> dict
  - Every agent logs its status to websocket_manager before and after running
  - Generated project files go in workspace/{project_name}/
  - All SerpApi calls go through backend/serpapi_client.py

## SerpApi Rules
  - ALWAYS use the `serpapi` Python package (not raw requests)
  - ALWAYS cache search results by query hash to avoid duplicate API calls
  - SerpApi is called ONLY inside the self-healing loop, not in other agents
  - Log every SerpApi call with query, result count, and timestamp
  - Handle rate limits gracefully: if 429, wait 2 seconds and retry once

## Error Handling
  - Every agent wraps its logic in try/except
  - On error, write to memory/errors.json with agent name, error, traceback,
    timestamp
  - On error, set agent status to ERROR and broadcast via WebSocket
  - Self-healing agent reads errors.json and attempts fixes

## Frontend Rules
  - No external JS libraries (no jQuery, no Bootstrap)
  - Use CSS Grid and Flexbox for layout
  - WebSocket reconnects automatically on disconnect
  - All API calls use fetch() with async/await
  - Show loading states for every async operation
  - Agent timeline animates smoothly using CSS transitions

## Testing
  - Unit tests for each agent in tests/
  - Integration test for the full pipeline
  - Mock SerpApi in tests (never call real API in tests)

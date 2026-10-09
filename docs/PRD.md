# DevSprint AI — Product Requirements Document

## 1. Problem
Code generators write code and hand it to you. If it's broken, that's your problem.
No tool properly asks what you want first, then verifies the final product matches
the original request. Students and beginners especially struggle because they
cannot debug generated code.

## 2. Solution
DevSprint AI is a multi-agent system that:
1. Asks clarifying questions one at a time (like Claude does)
2. Produces a Project Contract (JSON + Markdown)
3. Builds the code following the contract
4. Runs the code in a sandbox
5. Self-heals: reads errors, fixes code, re-runs (max 5 retries)
6. Uses SerpApi to search for current documentation and fixes when errors occur
7. Verifies the built product against the contract
   (frontend, backend, database, APIs, config, build)
8. Optionally generates a "Project Details" folder explaining everything in plain language

## 3. Target User
Students and beginners in India who have app ideas but limited coding experience.

## 4. SerpApi Integration (Hackathon Requirement)
SerpApi is used inside the self-healing loop. When generated code fails:
1. Extract the error type and library name from the error message
2. Call SerpApi Google Search with query: "{library} {error_message} fix"
3. Extract snippets from top 3 results
4. Pass snippets + error + code to the LLM for a fact-based fix

This prevents the LLM from hallucinating outdated APIs.
The agent fixes with current, search-verified information.

## 5. Track
AI Agents

## 6. Success Metrics
- System takes a one-sentence idea and produces working, tested code
- Self-healing loop succeeds in ≤5 retries for 80% of simple projects
- SerpApi is called at least once per self-healing cycle
- User can see which agent is working at every step
- Demo video shows the full pipeline end-to-end

## 7. Constraints
- Frontend: HTML, CSS, JavaScript only (no frameworks)
- Backend: Python (FastAPI for API layer, subprocess for code execution)
- LLM: One provider (OpenAI or Anthropic)
- Sandbox: Local subprocess (Docker is a later phase)
- Max retries in self-healing loop: 5
- No vector DB, no embeddings, no RAG (plain JSON files for memory)

## 8. Phases
Phase 1 — Core Loop + SerpApi
Phase 2 — Multi-Agent Architecture + Visualization
Phase 3 — Polish, Documentation, Demo Prep
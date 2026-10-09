<!-- Durable product context derived from the supplied Phase 1 brief and repository docs. -->
# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Students and beginning developers with a small Python tool idea and limited debugging experience.

## Product Purpose

DevSprint AI clarifies a natural-language idea, generates a project contract and architecture plan, waits for user approval, writes code and acceptance tests, runs them, verifies feature coverage, and documents the project. It attempts bounded repairs when execution fails.

## Operating Context

The user works in a browser beside a local FastAPI server. The current deliverable is Phase 2: a single Python CLI project at a time. Generated code runs on the local machine.

## Capabilities and Constraints

- Four clarification questions, one at a time.
- OpenAI generates the contract and Python source.
- Architecture produces a two-file plan and acceptance criteria before a hard approval pause.
- Users can edit the contract and regenerate the plan before approving the build.
- Test Writer generates criterion-mapped tests; Verifier reports layer and feature evidence.
- Verifier gaps can return to Coder for at most three revisions; Doc Agent creates a project README.
- Mermaid diagrams show workflow, architecture, and data flow from the contract and plan.
- SerpApi supplies search snippets during repair; calls are cached and logged.
- At most five repair attempts.
- HTML, CSS, vanilla JavaScript, FastAPI, JSON files, and local subprocess execution.

## Brand Commitments

The product is named DevSprint AI. The supplied design specifies a minimal dark three-panel workspace with teal status accents.

## Evidence on Hand

The governing brief and implementation details are in docs/PRD.md, docs/DESIGN.md, docs/AGENTS.md, and docs/SERPAPI_USAGE.md. No customer proof or live service credentials were supplied.

# Coordinate the approval-gated, verified DevSprint build pipeline.
"""Coordinate the approval-gated, verified DevSprint build pipeline."""

import asyncio
import os
import re
from typing import Any

from backend.agents.architecture_agent import ArchitectureAgent
from backend.agents.coder_agent import CoderAgent
from backend.agents.doc_agent import DocAgent
from backend.agents.executor_agent import ExecutorAgent
from backend.agents.requirements_agent import QUESTIONS, RequirementsAgent
from backend.agents.self_healing_agent import SelfHealingAgent
from backend.agents.test_writer_agent import TestWriterAgent
from backend.agents.verifier_agent import VerifierAgent
from backend.memory.shared_memory import (
    CONTRACT_FILE, ERRORS_FILE, FIXES_FILE, OUTPUT_FILE, PLAN_FILE, PROJECT_FILE,
    SERPAPI_CACHE_FILE, SERPAPI_LOG_FILE, VERIFICATION_FILE, read_json, write_json,
)
from backend.websocket_manager import websocket_manager

FINAL_FAILURE = "I couldn't fix this automatically. Please review the error."
VERIFICATION_FAILURE = "Verification still found gaps after three revisions. Please review the report."


class Orchestrator:
    """Own one project from clarification through approval and documentation."""

    def __init__(self) -> None:
        """Create agents and serialize project state changes."""
        self.requirements = RequirementsAgent()
        self.architecture = ArchitectureAgent()
        self.coder = CoderAgent()
        self.test_writer = TestWriterAgent()
        self.executor = ExecutorAgent()
        self.healer = SelfHealingAgent()
        self.verifier = VerifierAgent()
        self.doc = DocAgent()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def status(self) -> dict[str, Any]:
        """Return the durable project state and any pending question."""
        state = read_json(PROJECT_FILE)
        if state.get("phase") == "questions":
            index = len(state.get("answers", []))
            if index < len(QUESTIONS):
                state["question"] = QUESTIONS[index]
        return state

    async def start(self, idea: str) -> dict[str, Any]:
        """Start a fresh project and reset its generated memory files."""
        async with self._lock:
            if self._task and not self._task.done():
                raise RuntimeError("A project is still running. Wait for it to finish.")
            for path, default in (
                (CONTRACT_FILE, {}), (PLAN_FILE, {}), (VERIFICATION_FILE, {}),
                (ERRORS_FILE, []), (FIXES_FILE, []), (OUTPUT_FILE, {}),
                (SERPAPI_CACHE_FILE, {}), (SERPAPI_LOG_FILE, {"calls": []}),
            ):
                write_json(path, default)
            state = {
                "idea": idea.strip(), "answers": [], "phase": "questions",
                "agent": "Requirements", "attempt": 0, "verification_retry": 0,
                "completed_agents": [], "approved": False,
                "message": "Answer four questions to define the project.",
            }
            write_json(PROJECT_FILE, state)
            await self.requirements._set_status("working", "Gathering project requirements")
            await websocket_manager.broadcast({
                "type": "chat-message", "role": "agent", "message": QUESTIONS[0],
            })
            return self.status()

    async def answer(self, answer: str) -> dict[str, Any]:
        """Store one answer and prepare a contract and plan after the fourth."""
        async with self._lock:
            state = read_json(PROJECT_FILE)
            if state.get("phase") != "questions":
                raise RuntimeError("There is no pending question. Start a project first.")
            state["answers"].append(answer.strip())
            await websocket_manager.broadcast({
                "type": "chat-message", "role": "user", "message": answer.strip(),
            })
            if len(state["answers"]) < len(QUESTIONS):
                write_json(PROJECT_FILE, state)
                await websocket_manager.broadcast({
                    "type": "chat-message", "role": "agent",
                    "message": QUESTIONS[len(state["answers"])],
                })
                return self.status()
            state["phase"] = "planning"
            state["message"] = "Creating the contract and architecture plan"
            write_json(PROJECT_FILE, state)
            self._task = asyncio.create_task(self._prepare(state))
            return self.status()

    async def approve(self, approved: bool) -> dict[str, Any]:
        """Resume coding only after explicit approval of the saved contract."""
        async with self._lock:
            state = read_json(PROJECT_FILE)
            if not approved:
                raise RuntimeError("Approval must be true to start the build.")
            if state.get("phase") != "awaiting_approval":
                raise RuntimeError("The contract is not waiting for approval.")
            if not read_json(CONTRACT_FILE) or not read_json(PLAN_FILE):
                raise RuntimeError("The contract and architecture plan are required.")
            state["approved"] = True
            await self._publish(state, "building", "Coder", "Starting the approved build")
            self._task = asyncio.create_task(self._build(state))
            return self.status()

    async def edit_contract(self, contract: dict[str, Any]) -> dict[str, Any]:
        """Save user edits and regenerate the architecture before approval."""
        async with self._lock:
            state = read_json(PROJECT_FILE)
            if state.get("phase") != "awaiting_approval":
                raise RuntimeError("The contract can only be edited before approval.")
            name = str(contract.get("app_name", "")).strip()
            description = str(contract.get("description", "")).strip()
            if not name or not description:
                raise ValueError("The contract needs an app name and description.")
            cleaned = {"app_name": name, "description": description}
            for field in ("inputs", "outputs", "edge_cases"):
                values = contract.get(field)
                if not isinstance(values, list) or not all(
                    isinstance(item, str) for item in values
                ):
                    raise ValueError(f"{field} must be a list of strings.")
                cleaned[field] = [item.strip() for item in values if item.strip()]
            cleaned["project_name"] = (
                re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:50] or "project"
            )
            write_json(CONTRACT_FILE, cleaned)
            write_json(PLAN_FILE, {})
            await self._publish(state, "planning", "Architecture", "Updating the architecture plan")
            try:
                await self.architecture.execute(state, "Replanning the edited contract")
                self._mark_done(state, "Architecture")
                await self._ready_for_approval(state)
            except Exception as exc:
                await self._fail(state, f"Plan update stopped: {exc}")
            return self.status()

    async def _publish(self, state: dict[str, Any], phase: str,
                       agent: str, message: str) -> None:
        """Persist and broadcast one project transition."""
        state.update({"phase": phase, "agent": agent, "message": message})
        write_json(PROJECT_FILE, state)
        await websocket_manager.broadcast({"type": "project-status", **self.status()})

    def _mark_done(self, state: dict[str, Any], agent: str) -> None:
        """Remember completed agents so refreshes reconstruct the timeline."""
        completed = state.setdefault("completed_agents", [])
        if agent not in completed:
            completed.append(agent)
        write_json(PROJECT_FILE, state)

    async def _ready_for_approval(self, state: dict[str, Any]) -> None:
        """Publish the hard pause with both artifacts for the review modal."""
        await self._publish(
            state, "awaiting_approval", "",
            "Contract and architecture ready. Review and approve to start building.",
        )
        await websocket_manager.broadcast({
            "type": "contract-ready",
            "contract": read_json(CONTRACT_FILE), "plan": read_json(PLAN_FILE),
        })
        await websocket_manager.broadcast({
            "type": "chat-message", "role": "agent",
            "message": "Contract and architecture ready. Review and approve to start building.",
        })

    async def _prepare(self, state: dict[str, Any]) -> None:
        """Run Requirements and Architecture, then stop for approval."""
        try:
            await self._publish(state, "planning", "Requirements", "Creating the project contract")
            await self.requirements.execute(state, "Creating the project contract")
            self._mark_done(state, "Requirements")
            await self._publish(state, "planning", "Architecture", "Planning the Python project")
            await self.architecture.execute(state, "Planning files and acceptance criteria")
            self._mark_done(state, "Architecture")
            await self._ready_for_approval(state)
        except Exception as exc:
            await self._fail(state, f"Planning stopped: {exc}")

    async def _execute_with_repairs(self, state: dict[str, Any]) -> bool:
        """Run code and use SerpApi-guided repair up to five times."""
        limit = max(0, min(int(os.getenv("MAX_RETRIES", "5")), 5))
        for attempt in range(1, limit + 2):
            state["attempt"] = attempt
            await self._publish(state, "building", "Executor", f"Running attempt {attempt}")
            result = await self.executor.execute({"attempt": attempt},
                                                 f"Running attempt {attempt}")
            await websocket_manager.broadcast({"type": "output", **result})
            if result["success"]:
                self._mark_done(state, "Executor")
                return True
            if attempt > limit:
                await self._fail(state, FINAL_FAILURE)
                return False
            await self._publish(state, "building", "Self-Healing",
                                f"Researching fix {attempt} of {limit}")
            await self.healer.execute({"attempt": attempt},
                                      f"Searching SerpApi for fix {attempt}")
            self._mark_done(state, "Self-Healing")
            await websocket_manager.broadcast({"type": "files-updated"})
        return False

    async def _build(self, state: dict[str, Any]) -> None:
        """Run code, tests, execution, verification revisions, and documentation."""
        gaps: list[dict[str, str]] = []
        try:
            for revision in range(4):
                state["verification_retry"] = revision
                await self._publish(state, "building", "Coder",
                                    "Writing code" if revision == 0 else
                                    f"Closing verification gaps, revision {revision} of 3")
                await self.coder.execute({**state, "gaps": gaps}, "Writing Python code")
                self._mark_done(state, "Coder")
                await self._publish(state, "building", "Test Writer",
                                    "Writing acceptance tests")
                await self.test_writer.execute(state, "Writing tests from the plan")
                self._mark_done(state, "Test Writer")
                await websocket_manager.broadcast({"type": "files-updated"})
                if not await self._execute_with_repairs(state):
                    return
                await self._publish(state, "building", "Verifier",
                                    "Checking the contract layer by layer")
                verified = await self.verifier.execute(state, "Checking the approved criteria")
                self._mark_done(state, "Verifier")
                gaps = verified["gaps"]
                await websocket_manager.broadcast({
                    "type": "verification-ready", "report": verified["report"],
                })
                if not gaps:
                    await self._publish(state, "building", "Doc Agent",
                                        "Writing project documentation")
                    await self.doc.execute(state, "Writing the project README")
                    self._mark_done(state, "Doc Agent")
                    await websocket_manager.broadcast({"type": "files-updated"})
                    await self._publish(state, "complete", "", "Project built and verified.")
                    await websocket_manager.broadcast({
                        "type": "chat-message", "role": "agent",
                        "message": "Your project is ready. Code, tests, verification, and README are in the viewer.",
                    })
                    return
                if revision == 3:
                    await self._fail(state, VERIFICATION_FAILURE)
                    return
        except Exception as exc:
            await self._fail(state, f"Build stopped: {exc}")

    async def _fail(self, state: dict[str, Any], message: str) -> None:
        """Stop the pipeline and ask the user to review the failure."""
        await self._publish(state, "error", state.get("agent", ""), message)
        await websocket_manager.broadcast({
            "type": "chat-message", "role": "agent", "message": message,
        })


orchestrator = Orchestrator()

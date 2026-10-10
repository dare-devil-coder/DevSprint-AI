# Common lifecycle broadcasting and error capture for all agents.
"""Common lifecycle broadcasting and error capture for all agents."""

import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from backend.memory.shared_memory import ERRORS_FILE, append_json_list
from backend.memory import shared_memory as storage
from backend.memory.memory_manager import memory_manager
from backend.skills.skill_manager import skill_manager
from backend.utils.logger import log
from backend.websocket_manager import websocket_manager


class BaseAgent(ABC):
    """Execute an agent with visible working, done, and error transitions."""

    def __init__(self, name: str, icon: str) -> None:
        """Store the user-facing agent identity."""
        self.name = name
        self.icon = icon
        self._skills: list[dict[str, Any]] = []

    def skill_prompt(self, instruction: str) -> str:
        """Attach only the currently matched skill bodies to an agent instruction."""
        if not self._skills:
            return instruction
        names = ", ".join(item["name"] for item in self._skills)
        bodies = "\n\n".join(f"{item['name']}:\n{item['body']}" for item in self._skills)
        return f"{instruction}\n\nActive skills: {names}\nSkill rules:\n{bodies}"

    @abstractmethod
    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Perform this agent's work and return its result."""

    async def _set_status(self, status: str, message: str = "") -> None:
        """Publish a lifecycle transition to the browser."""
        log(self.name, status, message)
        await websocket_manager.broadcast({"type": "agent-status", "agent": self.name,
                                           "icon": self.icon, "status": status, "message": message})

    async def execute(self, context: dict[str, Any], message: str = "") -> dict[str, Any]:
        """Wrap run with status updates and durable exception records."""
        contract = storage.read_json(storage.CONTRACT_FILE)
        project_type = contract.get("project_type", "python_cli")
        language = "python" if project_type == "python_cli" else "html_css_javascript"
        task = {"agent": self.name, "description": message,
                "language": language if self.name in {"Coder", "Test Writer", "Self-Healing", "Verifier"} else "",
                "file_path": "test_main.py" if self.name == "Test Writer" else
                             "main.py" if project_type == "python_cli" and self.name in {"Coder", "Self-Healing"} else
                             "app.js" if project_type == "web_app" and self.name in {"Coder", "Self-Healing"} else ""}
        self._skills = skill_manager.load_skills_for(task)
        scoped = memory_manager.get_for_agent(self.name, task)
        scoped.update(context)
        scoped["session_summary"] = memory_manager.summarize_session()
        scoped["memory"] = {key: value for key, value in scoped.items()
                            if key in {"contract", "plan", "files", "allowed_files", "errors", "fixes", "output", "verification"}}
        names = [item["name"] for item in self._skills]
        state = storage.read_json(storage.PROJECT_FILE)
        if state.get("agent") == self.name:
            state["active_skills"] = names
            storage.write_json(storage.PROJECT_FILE, state)
        await websocket_manager.broadcast({"type": "skills-active", "skills": names})
        for name in names:
            memory_manager.remember_decision(self.name, f"Activated skill: {name}",
                                             f"Matched the {self.name} task.")
        await self._set_status("working", message)
        try:
            result = await self.run(scoped)
        except Exception as exc:
            append_json_list(ERRORS_FILE, {
                "agent": self.name, "error": str(exc), "traceback": traceback.format_exc(),
                "feature": "agent execution", "file": "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await self._set_status("error", str(exc))
            raise
        await self._set_status("error" if result.get("success") is False else "done",
                               result.get("message", "Complete"))
        return result

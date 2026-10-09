# Common lifecycle broadcasting and error capture for all agents.
"""Common lifecycle broadcasting and error capture for all agents."""

import traceback
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from backend.memory.shared_memory import ERRORS_FILE, append_json_list
from backend.utils.logger import log
from backend.websocket_manager import websocket_manager


class BaseAgent(ABC):
    """Execute an agent with visible working, done, and error transitions."""

    def __init__(self, name: str, icon: str) -> None:
        """Store the user-facing agent identity."""
        self.name = name
        self.icon = icon

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
        await self._set_status("working", message)
        try:
            result = await self.run(context)
        except Exception as exc:
            append_json_list(ERRORS_FILE, {
                "agent": self.name, "error": str(exc), "traceback": traceback.format_exc(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            await self._set_status("error", str(exc))
            raise
        await self._set_status("error" if result.get("success") is False else "done",
                               result.get("message", "Complete"))
        return result

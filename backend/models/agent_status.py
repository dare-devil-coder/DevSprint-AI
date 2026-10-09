# Agent lifecycle states sent to the browser.
"""Agent lifecycle states sent to the browser."""

from enum import Enum


class AgentStatus(str, Enum):
    """The four visible states of an agent."""

    IDLE = "idle"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"

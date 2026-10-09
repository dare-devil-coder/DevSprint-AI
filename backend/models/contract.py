# The agreed shape of a generated Python project.
"""The agreed shape of a generated Python project."""

from dataclasses import dataclass


@dataclass
class ProjectContract:
    """Structured requirements handed from clarification to coding."""

    app_name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    edge_cases: list[str]

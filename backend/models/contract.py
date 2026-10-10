# The agreed shape and target experience of a generated project.
"""Structured requirements for either a browser prototype or Python CLI."""

from dataclasses import dataclass


@dataclass
class ProjectContract:
    """Structured requirements handed from clarification to project agents."""

    app_name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    edge_cases: list[str]
    project_type: str = "python_cli"
    design_direction: str = ""

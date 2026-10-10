# Small structured console logger for agent transitions.
"""Small structured console logger for agent transitions."""

import sys


def log(agent: str, status: str, message: str) -> None:
    """Write a readable lifecycle line to the server console."""
    line = f"[{agent}] [{status.upper()}] {message}"
    encoding = sys.stdout.encoding or "utf-8"
    print(line.encode(encoding, errors="backslashreplace").decode(encoding), flush=True)

# Small structured console logger for agent transitions.
"""Small structured console logger for agent transitions."""


def log(agent: str, status: str, message: str) -> None:
    """Write a readable lifecycle line to the server console."""
    print(f"[{agent}] [{status.upper()}] {message}", flush=True)

# Broadcast agent and project events to all connected browsers.
"""Broadcast agent and project events to all connected browsers."""

import asyncio

from fastapi import WebSocket


class WebSocketManager:
    """Track live WebSocket clients and safely remove disconnected ones."""

    def __init__(self) -> None:
        """Initialize an empty connection registry."""
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a browser connection."""
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a closed browser connection."""
        self.connections.discard(websocket)

    async def broadcast(self, event: dict) -> None:
        """Send an event to every live connection without blocking on one client."""
        if not self.connections:
            return
        clients = tuple(self.connections)
        results = await asyncio.gather(
            *(client.send_json(event) for client in clients), return_exceptions=True
        )
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                self.disconnect(client)


websocket_manager = WebSocketManager()

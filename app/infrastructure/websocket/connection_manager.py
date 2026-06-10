import asyncio
import logging
from typing import Set

from fastapi import WebSocket

logger = logging.getLogger("chatbot.websocket")


class ConnectionManager:
    """Manages the set of active WebSocket connections from the frontend.

    Responsibilities:
    - Accept and track connections.
    - Broadcast JSON payloads to all connected clients.
    - Silently drop stale connections discovered during broadcast.

    All public methods are async and safe to call concurrently.
    """

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept the handshake and register the connection."""
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        logger.info(
            "Frontend connected — total connections: %d", len(self._connections)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a connection from the active set."""
        async with self._lock:
            self._connections.discard(websocket)
        logger.info(
            "Frontend disconnected — total connections: %d", len(self._connections)
        )

    async def broadcast(self, data: dict) -> None:
        """Send *data* as JSON to every connected client.

        Any connection that fails to receive the message is removed from the
        active set so that future broadcasts are not blocked by dead sockets.
        """
        # Snapshot the current set so we don't hold the lock during I/O.
        async with self._lock:
            connections = set(self._connections)

        dead: Set[WebSocket] = set()
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception as exc:
                logger.warning("Failed to send to WebSocket client: %s", exc)
                dead.add(ws)

        if dead:
            async with self._lock:
                self._connections -= dead
            logger.debug("Removed %d stale connection(s)", len(dead))

    @property
    def active_count(self) -> int:
        """Number of currently registered connections (not coroutine-safe for decisions)."""
        return len(self._connections)

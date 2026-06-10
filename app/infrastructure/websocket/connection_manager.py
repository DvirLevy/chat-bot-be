import asyncio
import logging
from typing import Dict

from fastapi import WebSocket

logger = logging.getLogger("chatbot.websocket")


class ConnectionManager:
    """Manages active WebSocket connections, keyed by frontend username.

    Responsibilities:
    - Accept and track connections per username.
    - Broadcast JSON payloads to all connected clients.
    - Send a JSON payload to a single user's connection.
    - Silently drop stale connections discovered during send/broadcast.

    All public methods are async and safe to call concurrently.
    """

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, username: str, websocket: WebSocket) -> None:
        """Accept the handshake and register the connection under *username*.

        A new connection for an already-registered username replaces the
        previous one.
        """
        await websocket.accept()
        async with self._lock:
            self._connections[username] = websocket
        logger.info(
            "Frontend connected — username=%s, total connections: %d",
            username,
            len(self._connections),
        )

    async def disconnect(self, username: str) -> None:
        """Remove *username*'s connection from the active map."""
        async with self._lock:
            self._connections.pop(username, None)
        logger.info(
            "Frontend disconnected — username=%s, total connections: %d",
            username,
            len(self._connections),
        )

    async def send_to(self, username: str, data: dict) -> None:
        """Send *data* as JSON to *username*'s connection, if any.

        If the connection is dead or missing, it is silently dropped.
        """
        async with self._lock:
            websocket = self._connections.get(username)

        if websocket is None:
            logger.debug("send_to: no connection registered for username=%s", username)
            return

        try:
            await websocket.send_json(data)
        except Exception as exc:
            logger.warning("Failed to send to username=%s: %s", username, exc)
            async with self._lock:
                self._connections.pop(username, None)

    async def broadcast(self, data: dict) -> None:
        """Send *data* as JSON to every connected client.

        Any connection that fails to receive the message is removed from the
        active map so that future broadcasts are not blocked by dead sockets.
        """
        # Snapshot the current connections so we don't hold the lock during I/O.
        async with self._lock:
            connections = dict(self._connections)

        dead: list[str] = []
        for username, ws in connections.items():
            try:
                await ws.send_json(data)
            except Exception as exc:
                logger.warning("Failed to send to username=%s: %s", username, exc)
                dead.append(username)

        if dead:
            async with self._lock:
                for username in dead:
                    self._connections.pop(username, None)
            logger.debug("Removed %d stale connection(s)", len(dead))

    @property
    def active_count(self) -> int:
        """Number of currently registered connections (not coroutine-safe for decisions)."""
        return len(self._connections)

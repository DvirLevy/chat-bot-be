import asyncio
import logging
from typing import Dict

from fastapi import WebSocket

from app.models.websocket_events import SessionReplacedEvent

logger = logging.getLogger("chatbot.websocket")


class ConnectionManager:

    def __init__(self) -> None:
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, username: str, websocket: WebSocket) -> None:
        async with self._lock:
            previous = self._connections.get(username)
            self._connections[username] = websocket

        if previous is not None and previous is not websocket:
            try:
                await previous.send_json(SessionReplacedEvent().model_dump())
                await previous.close()
            except Exception as exc:
                logger.warning(
                    "Failed to close replaced connection for username=%s: %s",
                    username,
                    exc,
                )

        logger.info(
            "Frontend connected — username=%s, total connections: %d",
            username,
            len(self._connections),
        )

    async def disconnect(self, username: str, websocket: WebSocket) -> bool:
        async with self._lock:
            if self._connections.get(username) is websocket:
                self._connections.pop(username, None)
                removed = True
            else:
                removed = False
        logger.info(
            "Frontend disconnected — username=%s, total connections: %d",
            username,
            len(self._connections),
        )
        return removed

    async def send_to(self, username: str, data: dict) -> None:
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
        return len(self._connections)

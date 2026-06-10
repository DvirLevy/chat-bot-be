"""
Integration tests for the WebSocket protocol: join/history/busy/turn_granted
and disconnect-releases-active behaviour.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.websocket import router as ws_router
from app.bl.chat_service import ChatService
from app.dal.memory.in_memory_chat_state_repository import InMemoryChatStateRepository
from app.dal.memory.in_memory_message_repository import InMemoryMessageRepository
from app.dal.memory.in_memory_user_repository import InMemoryUserRepository
from app.infrastructure.websocket.connection_manager import ConnectionManager


@pytest.fixture
def app() -> FastAPI:
    application = FastAPI()
    application.include_router(ws_router)

    telegram_client = MagicMock()
    telegram_client.send_message = AsyncMock()
    connection_manager = ConnectionManager()

    application.state.chat_service = ChatService(
        message_repo=InMemoryMessageRepository(),
        chat_state_repo=InMemoryChatStateRepository(),
        connection_manager=connection_manager,
        telegram_client=telegram_client,
        user_repo=InMemoryUserRepository(),
    )
    application.state.connection_manager = connection_manager
    return application


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _join(ws, username: str) -> None:
    ws.receive_json()  # status
    ws.send_json({"type": "join", "username": username})


def test_join_returns_history_then_turn_granted(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        _join(ws, "alice")

        history = ws.receive_json()
        assert history["type"] == "history"
        assert history["messages"] == []

        granted = ws.receive_json()
        assert granted["type"] == "turn_granted"


def test_second_user_receives_busy(client: TestClient) -> None:
    with client.websocket_connect("/ws") as alice_ws:
        _join(alice_ws, "alice")
        alice_ws.receive_json()  # history
        alice_ws.receive_json()  # turn_granted

        with client.websocket_connect("/ws") as bob_ws:
            _join(bob_ws, "bob")
            busy = bob_ws.receive_json()
            assert busy["type"] == "busy"


def test_disconnect_releases_active_slot(client: TestClient) -> None:
    with client.websocket_connect("/ws") as alice_ws:
        _join(alice_ws, "alice")
        alice_ws.receive_json()  # history
        alice_ws.receive_json()  # turn_granted

    # alice_ws is now closed -> disconnect should release the active slot.

    with client.websocket_connect("/ws") as bob_ws:
        _join(bob_ws, "bob")
        history = bob_ws.receive_json()
        assert history["type"] == "history"
        granted = bob_ws.receive_json()
        assert granted["type"] == "turn_granted"


def test_end_chat_releases_active_slot(client: TestClient) -> None:
    with client.websocket_connect("/ws") as alice_ws:
        _join(alice_ws, "alice")
        alice_ws.receive_json()  # history
        alice_ws.receive_json()  # turn_granted

        alice_ws.send_json({"type": "end_chat"})

        with client.websocket_connect("/ws") as bob_ws:
            _join(bob_ws, "bob")
            history = bob_ws.receive_json()
            assert history["type"] == "history"
            granted = bob_ws.receive_json()
            assert granted["type"] == "turn_granted"


def test_returning_user_receives_their_history(client: TestClient) -> None:
    with client.websocket_connect("/ws") as alice_ws:
        _join(alice_ws, "alice")
        alice_ws.receive_json()  # history (empty)
        alice_ws.receive_json()  # turn_granted

        alice_ws.send_json({"type": "send_message", "text": "hello"})
        alice_ws.send_json({"type": "end_chat"})

    with client.websocket_connect("/ws") as alice_ws2:
        _join(alice_ws2, "alice")
        history = alice_ws2.receive_json()
        assert history["type"] == "history"
        assert len(history["messages"]) == 1
        assert history["messages"][0]["text"] == "hello"


def test_busy_user_cannot_send_message(client: TestClient) -> None:
    with client.websocket_connect("/ws") as alice_ws:
        _join(alice_ws, "alice")
        alice_ws.receive_json()  # history
        alice_ws.receive_json()  # turn_granted

        with client.websocket_connect("/ws") as bob_ws:
            _join(bob_ws, "bob")
            bob_ws.receive_json()  # busy

            bob_ws.send_json({"type": "send_message", "text": "sneaky"})
            response = bob_ws.receive_json()
            assert response["type"] == "busy"

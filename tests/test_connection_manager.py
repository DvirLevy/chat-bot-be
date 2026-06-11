"""
Tests for ConnectionManager: per-username connection tracking and targeted send.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure.websocket.connection_manager import ConnectionManager


def make_websocket() -> MagicMock:
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_send_to_reaches_only_target_connection() -> None:
    manager = ConnectionManager()
    alice_ws = make_websocket()
    bob_ws = make_websocket()

    await manager.connect("alice", alice_ws)
    await manager.connect("bob", bob_ws)

    await manager.send_to("alice", {"type": "message", "payload": "hi"})

    alice_ws.send_json.assert_awaited_once_with({"type": "message", "payload": "hi"})
    bob_ws.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_to_unknown_username_is_noop() -> None:
    manager = ConnectionManager()
    alice_ws = make_websocket()
    await manager.connect("alice", alice_ws)

    await manager.send_to("nobody", {"type": "message"})

    alice_ws.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_disconnect_removes_connection() -> None:
    manager = ConnectionManager()
    alice_ws = make_websocket()
    await manager.connect("alice", alice_ws)

    removed = await manager.disconnect("alice", alice_ws)

    assert removed is True
    assert manager.active_count == 0
    await manager.send_to("alice", {"type": "message"})
    alice_ws.send_json.assert_not_awaited()


@pytest.mark.asyncio
async def test_disconnect_of_replaced_connection_is_noop() -> None:
    """A stale connection that was already replaced must not remove the
    newer one when it disconnects."""
    manager = ConnectionManager()
    first_ws = make_websocket()
    second_ws = make_websocket()

    await manager.connect("alice", first_ws)
    await manager.connect("alice", second_ws)

    removed = await manager.disconnect("alice", first_ws)

    assert removed is False
    assert manager.active_count == 1
    await manager.send_to("alice", {"type": "message"})
    second_ws.send_json.assert_awaited_once_with({"type": "message"})


@pytest.mark.asyncio
async def test_reconnect_replaces_previous_connection() -> None:
    manager = ConnectionManager()
    first_ws = make_websocket()
    second_ws = make_websocket()

    await manager.connect("alice", first_ws)
    await manager.connect("alice", second_ws)

    await manager.send_to("alice", {"type": "message"})

    second_ws.send_json.assert_awaited_once()
    assert manager.active_count == 1


@pytest.mark.asyncio
async def test_reconnect_notifies_and_closes_previous_connection() -> None:
    manager = ConnectionManager()
    first_ws = make_websocket()
    second_ws = make_websocket()

    await manager.connect("alice", first_ws)
    await manager.connect("alice", second_ws)

    first_ws.send_json.assert_awaited_once_with({"type": "session_replaced"})
    first_ws.close.assert_awaited_once()
    second_ws.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_reaches_all_connections() -> None:
    manager = ConnectionManager()
    alice_ws = make_websocket()
    bob_ws = make_websocket()
    await manager.connect("alice", alice_ws)
    await manager.connect("bob", bob_ws)

    await manager.broadcast({"type": "status"})

    alice_ws.send_json.assert_awaited_once_with({"type": "status"})
    bob_ws.send_json.assert_awaited_once_with({"type": "status"})

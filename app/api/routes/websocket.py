import json
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.bl.chat_service import ChatService
from app.infrastructure.websocket.connection_manager import ConnectionManager
from app.models.websocket_events import (
    BusyEvent,
    EndChatEvent,
    ErrorEvent,
    HistoryEvent,
    JoinEvent,
    SendMessageEvent,
    StatusEvent,
    TurnGrantedEvent,
)

logger = logging.getLogger("chatbot.ws_route")

router = APIRouter(tags=["websocket"])

_INVALID_FORMAT_MESSAGE = (
    "Invalid message format. Expected one of: "
    '{"type": "join", "username": "..."}, '
    '{"type": "send_message", "text": "..."}, '
    '{"type": "end_chat"}'
)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time bidirectional channel between the React frontend and the service.

    Protocol
    --------
    On connect:
        Backend → Frontend: StatusEvent

    First frontend message must be a join event:
        {"type": "join", "username": "..."}
        - Upserts the user and tries to become the active participant.
        - If accepted: Backend → Frontend: HistoryEvent, then TurnGrantedEvent.
        - If another user is active: Backend → Frontend: BusyEvent.

    Subsequent frontend messages:
        {"type": "send_message", "text": "..."}
            Routed via ChatService.
        {"type": "end_chat"}
            Releases the active slot if held by this user.

    On parse / validation error:
        Backend → Frontend: ErrorEvent

    On disconnect:
        Connection is removed from the manager and the active slot is
        released if it was held by this user.
    """
    chat_service: ChatService = websocket.app.state.chat_service
    connection_manager: ConnectionManager = websocket.app.state.connection_manager

    await websocket.accept()
    logger.info("WebSocket connection accepted")

    # Notify the client about current session state.
    active_username = await chat_service.get_active_username()
    status_event = StatusEvent(
        connected=True,
        active_participant=active_username is not None,
    )
    await websocket.send_json(status_event.model_dump())

    username: Optional[str] = None

    try:
        while True:
            raw = await websocket.receive_text()
            logger.debug("Received raw WebSocket message (len=%d)", len(raw))

            try:
                payload = json.loads(raw)
                event_type = payload.get("type")
            except Exception as exc:
                logger.warning("Invalid WebSocket message: %s — raw: %.120s", exc, raw)
                error = ErrorEvent(message=_INVALID_FORMAT_MESSAGE)
                await websocket.send_json(error.model_dump())
                continue

            if event_type == "join":
                try:
                    join_event = JoinEvent(**payload)
                except Exception as exc:
                    logger.warning("Invalid join event: %s — raw: %.120s", exc, raw)
                    error = ErrorEvent(message=_INVALID_FORMAT_MESSAGE)
                    await websocket.send_json(error.model_dump())
                    continue

                username = join_event.username
                assigned = await chat_service.assign_active_user(username)
                await connection_manager.connect(username, websocket)

                if assigned:
                    history = await chat_service.get_history(username)
                    history_event = HistoryEvent(messages=history)
                    await websocket.send_json(history_event.model_dump())
                    await websocket.send_json(TurnGrantedEvent().model_dump())
                else:
                    await websocket.send_json(BusyEvent().model_dump())
                continue

            if username is None:
                error = ErrorEvent(message="Must send a 'join' event first.")
                await websocket.send_json(error.model_dump())
                continue

            if event_type == "send_message":
                try:
                    event = SendMessageEvent(**payload)
                except Exception as exc:
                    logger.warning("Invalid send_message event: %s — raw: %.120s", exc, raw)
                    error = ErrorEvent(message=_INVALID_FORMAT_MESSAGE)
                    await websocket.send_json(error.model_dump())
                    continue

                if not event.text.strip():
                    error = ErrorEvent(message="Message text must not be empty.")
                    await websocket.send_json(error.model_dump())
                    continue

                if await chat_service.get_active_username() != username:
                    await websocket.send_json(BusyEvent().model_dump())
                    continue

                await chat_service.handle_frontend_message(event.text, username=username)

            elif event_type == "end_chat":
                EndChatEvent(**payload)
                await chat_service.release_active_if(username)

            else:
                error = ErrorEvent(message=_INVALID_FORMAT_MESSAGE)
                await websocket.send_json(error.model_dump())

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        if username is not None:
            await connection_manager.disconnect(username)
            await chat_service.release_active_if(username)

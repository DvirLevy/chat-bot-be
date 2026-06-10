import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.bl.chat_service import ChatService
from app.infrastructure.websocket.connection_manager import ConnectionManager
from app.models.websocket_events import ErrorEvent, SendMessageEvent, StatusEvent

logger = logging.getLogger("chatbot.ws_route")

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time bidirectional channel between the React frontend and the service.

    Protocol
    --------
    On connect:
        Backend → Frontend: StatusEvent

    On each frontend message:
        Expected JSON: {"type": "send_message", "text": "..."}
        Backend validates, routes via ChatService, and echoes nothing (the
        outgoing message is already stored; Telegram delivery is fire-and-forget
        from the frontend's perspective).

    On parse / validation error:
        Backend → Frontend: ErrorEvent

    On disconnect:
        Connection is silently removed from the manager.
    """
    chat_service: ChatService = websocket.app.state.chat_service
    connection_manager: ConnectionManager = websocket.app.state.connection_manager

    await connection_manager.connect(websocket)
    logger.info("WebSocket connection accepted")

    # Notify the client about current session state.
    active_username = await chat_service.get_active_username()
    status_event = StatusEvent(
        connected=True,
        active_participant=active_username is not None,
    )
    await websocket.send_json(status_event.model_dump())

    try:
        while True:
            raw = await websocket.receive_text()
            logger.debug("Received raw WebSocket message (len=%d)", len(raw))

            try:
                payload = json.loads(raw)
                event = SendMessageEvent(**payload)
            except Exception as exc:
                logger.warning("Invalid WebSocket message: %s — raw: %.120s", exc, raw)
                error = ErrorEvent(message="Invalid message format. Expected: {\"type\": \"send_message\", \"text\": \"...\"}")
                await websocket.send_json(error.model_dump())
                continue

            if not event.text.strip():
                error = ErrorEvent(message="Message text must not be empty.")
                await websocket.send_json(error.model_dump())
                continue

            # TODO: BE-6 replaces "default" with the real username from the join event.
            await chat_service.handle_frontend_message(event.text, username="default")

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        await connection_manager.disconnect(websocket)

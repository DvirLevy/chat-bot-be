"""
WebSocket event envelope types.

Frontend → Backend:
    SendMessageEvent  {"type": "send_message", "text": "..."}

Backend → Frontend:
    MessageEvent      {"type": "message", "payload": <Message>}
    ErrorEvent        {"type": "error", "message": "..."}
    StatusEvent       {"type": "status", "connected": bool, "active_participant": bool}
"""

from typing import Literal

from pydantic import BaseModel

from app.models.message import Message


# ── Inbound (frontend → backend) ─────────────────────────────────────────────

class SendMessageEvent(BaseModel):
    type: Literal["send_message"]
    text: str


# ── Outbound (backend → frontend) ────────────────────────────────────────────

class MessageEvent(BaseModel):
    type: Literal["message"] = "message"
    payload: Message


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


class StatusEvent(BaseModel):
    type: Literal["status"] = "status"
    connected: bool
    active_participant: bool

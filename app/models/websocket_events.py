"""
WebSocket event envelope types.

Frontend → Backend:
    JoinEvent         {"type": "join", "username": "..."}
    SendMessageEvent  {"type": "send_message", "text": "..."}
    EndChatEvent      {"type": "end_chat"}

Backend → Frontend:
    MessageEvent      {"type": "message", "payload": <Message>}
    ErrorEvent        {"type": "error", "message": "..."}
    StatusEvent       {"type": "status", "connected": bool, "active_participant": bool}
    IdleTimeoutEvent  {"type": "idle_timeout", "username": "..."}
    HistoryEvent      {"type": "history", "messages": [<Message>, ...]}
    BusyEvent         {"type": "busy"}
    TurnGrantedEvent  {"type": "turn_granted"}
    SessionReplacedEvent {"type": "session_replaced"}
"""

from typing import List, Literal

from pydantic import BaseModel

from app.models.message import Message


# ── Inbound (frontend → backend) ─────────────────────────────────────────────

class JoinEvent(BaseModel):
    type: Literal["join"]
    username: str


class SendMessageEvent(BaseModel):
    type: Literal["send_message"]
    text: str


class EndChatEvent(BaseModel):
    type: Literal["end_chat"]


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


class IdleTimeoutEvent(BaseModel):
    type: Literal["idle_timeout"] = "idle_timeout"
    username: str


class HistoryEvent(BaseModel):
    type: Literal["history"] = "history"
    messages: List[Message]


class BusyEvent(BaseModel):
    type: Literal["busy"] = "busy"


class TurnGrantedEvent(BaseModel):
    type: Literal["turn_granted"] = "turn_granted"


class SessionReplacedEvent(BaseModel):
    type: Literal["session_replaced"] = "session_replaced"

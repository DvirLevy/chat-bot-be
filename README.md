# Chat Bridge — Backend

A production-quality FastAPI backend that bridges a React frontend and a single
Telegram user via a WebSocket connection and the Telegram Bot API.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Folder Structure](#folder-structure)
4. [Key Design Decisions](#key-design-decisions)
5. [Telegram Bot Setup](#telegram-bot-setup)
6. [Environment Setup](#environment-setup)
7. [Running Locally](#running-locally)
8. [Running with Docker](#running-with-docker)
9. [Running Tests](#running-tests)
10. [API Reference](#api-reference)
11. [Trade-offs and Assumptions](#trade-offs-and-assumptions)

---

## Project Overview

```
React Frontend  ──WebSocket──►  FastAPI Backend  ──Bot API──►  Telegram User
                ◄─────────────                  ◄────────────
```

The backend acts as a stateful relay:

- A single Telegram user sends messages → the backend forwards them to all
  connected frontend clients over WebSocket.
- The frontend sends a message → the backend delivers it to the active Telegram
  user via the Bot API.
- Only the **first** Telegram user to message the bot becomes the active
  participant.  Any subsequent Telegram user receives a rejection notice.

---

## Architecture

The codebase follows a strict layered architecture.  Each layer has a single
responsibility and depends only on layers below it.

```
┌─────────────────────────────────────────┐
│              API Layer                  │  FastAPI routes, WebSocket endpoint,
│          app/api/routes/                │  request validation, response models
└───────────────────┬─────────────────────┘
                    │ calls
┌───────────────────▼─────────────────────┐
│         Business Logic Layer            │  Orchestration, routing rules,
│            app/bl/                      │  participant management, concurrency
└──────┬───────────────────┬──────────────┘
       │ reads/writes       │ delegates I/O
┌──────▼──────────┐  ┌──────▼──────────────────┐
│   DAL Layer     │  │   Infrastructure Layer   │
│   app/dal/      │  │   app/infrastructure/    │
│                 │  │                          │
│  Repositories   │  │  Telegram Bot client     │
│  (abstract +    │  │  WebSocket connection    │
│  in-memory)     │  │  manager                 │
└─────────────────┘  └──────────────────────────┘
```

### Layers

| Layer | Path | Responsibility |
|-------|------|---------------|
| **API** | `app/api/` | FastAPI routes, WebSocket endpoint, input validation, response serialisation |
| **BL** | `app/bl/` | `ChatService` — chat orchestration, message routing, participant management, concurrency protection |
| **DAL** | `app/dal/` | Repository abstractions (`MessageRepository`, `ChatStateRepository`) and their in-memory implementations |
| **Infrastructure** | `app/infrastructure/` | `TelegramClient` (python-telegram-bot wrapper), `TelegramUpdateHandler` (callback bridge), `ConnectionManager` (WebSocket state) |
| **Models** | `app/models/` | Shared Pydantic models (`Message`, WebSocket event envelopes, `TelegramUser`) |
| **Core** | `app/core/` | Configuration (`pydantic-settings`), logging setup |
| **Helpers** | `app/helpers/` | Pure utility functions — UUID generation, UTC timestamp formatting |

---

## Folder Structure

```
backend/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── health.py          # GET /health
│   │       └── websocket.py       # WS /ws
│   │
│   ├── bl/
│   │   └── chat_service.py        # Core orchestration
│   │
│   ├── dal/
│   │   ├── repositories/
│   │   │   ├── message_repository.py
│   │   │   └── chat_state_repository.py
│   │   └── memory/
│   │       ├── in_memory_message_repository.py
│   │       └── in_memory_chat_state_repository.py
│   │
│   ├── infrastructure/
│   │   ├── telegram/
│   │   │   ├── telegram_client.py
│   │   │   └── telegram_update_handler.py
│   │   └── websocket/
│   │       └── connection_manager.py
│   │
│   ├── helpers/
│   │   ├── id_helper.py
│   │   └── time_helper.py
│   │
│   ├── models/
│   │   ├── message.py
│   │   ├── websocket_events.py
│   │   └── telegram_models.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   │
│   └── main.py
│
├── tests/
│   ├── conftest.py
│   ├── test_chat_service.py
│   ├── test_single_active_chat.py
│   └── test_message_ordering.py
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── pytest.ini
├── CLAUDE.md
└── README.md
```

---

## Key Design Decisions

### Why WebSocket?

The frontend needs to receive messages the moment they arrive from Telegram —
there is no user action that triggers a poll.  WebSocket provides a persistent,
full-duplex channel that allows the server to push messages to the client at any
time without the overhead and latency of HTTP polling.

Alternatives considered:

- **Server-Sent Events (SSE)**: uni-directional (server → client only).  A
  second HTTP channel would be needed for outgoing messages, complicating the
  protocol.
- **Long polling**: higher latency, more server resource consumption, and more
  complex retry logic on the client.

### Why In-Memory State?

The assignment explicitly scopes state to the current server session.  A
database would add operational complexity (connection management, migrations,
seeding) with no benefit for a single-session demo.  The `MessageRepository`
and `ChatStateRepository` abstractions mean swapping to a persistent store (e.g.
Redis, PostgreSQL) requires only new implementations of those interfaces — the
business logic layer is untouched.

### Single Active Participant

The first Telegram user to send a message is registered as the active
participant (`active_chat_id`).  All subsequent Telegram users receive a polite
rejection message.  This assignment is protected by a double-checked locking
pattern:

1. Optimistic read (no lock) — returns immediately in the common case where an
   active participant is already set.
2. If the slot appears empty, acquire `_assign_lock`, then re-read inside the
   lock to guard against the race where two coroutines both see `None` before
   either writes.

### Concurrency Safety

Python's asyncio event loop is single-threaded, but `await` points are
preemption points where another coroutine can run.  Any operation that spans
multiple `await` calls and must be atomic uses an `asyncio.Lock`:

- `ChatService._assign_lock`: atomic check-then-set for participant assignment.
- `InMemoryChatStateRepository._lock`: atomic increment of the sequence counter.
- `InMemoryMessageRepository._lock`: serialised list mutations.
- `ConnectionManager._lock`: serialised set mutations.

### Message Ordering

Every message (incoming and outgoing) receives a sequence number from a shared
counter that increments atomically inside a lock.  The counter is never reset
during a session, so sequence values are globally unique and strictly ascending
across all message directions.

---

## Telegram Bot Setup

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot` and follow the prompts to choose a name and username.
3. BotFather will reply with your bot token, e.g.
   `123456789:AAHdqTcvCH1vGWJxfSeofSs4tGeaae38-1o`
4. Copy this token into your `.env` file as `TELEGRAM_BOT_TOKEN`.
5. Send your bot a message from the Telegram account that should be the active
   participant — this triggers the first-message assignment.

---

## Environment Setup

```bash
cp .env.example .env
# Edit .env and set TELEGRAM_BOT_TOKEN to your actual bot token.
```

---

## Running Locally

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at:
- Health check: http://localhost:8000/health
- WebSocket: ws://localhost:8000/ws
- Interactive docs: http://localhost:8000/docs

---

## Running with Docker

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN

# 2. Build and start
docker compose up --build

# 3. Stop
docker compose down
```

---

## Running Tests

```bash
# From the backend/ directory with dependencies installed:
pytest

# Verbose output:
pytest -v

# Specific test file:
pytest tests/test_message_ordering.py -v
```

All tests use real in-memory repositories and mock only the I/O boundaries
(`TelegramClient.send_message`, `ConnectionManager.broadcast`).

---

## API Reference

### `GET /health`

Returns service liveness.

**Response**
```json
{ "status": "healthy" }
```

---

### `WS /ws`

Real-time bidirectional channel.

**On connect** the server immediately sends:
```json
{ "type": "status", "connected": true, "active_participant": false }
```

**Frontend → Backend** (send a message):
```json
{ "type": "send_message", "text": "Hello from the frontend" }
```

**Backend → Frontend** (incoming Telegram message):
```json
{
  "type": "message",
  "payload": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "text": "Hello from Telegram",
    "direction": "incoming",
    "timestamp": "2024-01-15T10:30:00.000000+00:00",
    "sequence": 1
  }
}
```

**Backend → Frontend** (error):
```json
{ "type": "error", "message": "Invalid message format. Expected: ..." }
```

---

## Trade-offs and Assumptions

| Area | Decision | Trade-off |
|------|----------|-----------|
| **State persistence** | In-memory only | State is lost on restart; acceptable for a session demo |
| **Active participant** | First-come, first-served; no reset mechanism | Simplest policy; a real app might add an admin endpoint to reset the session |
| **Multiple frontend clients** | All connected WebSocket clients receive all messages | Suitable for a demo; a real app might scope sessions by user |
| **Outgoing message echo** | Not echoed back to frontend (no `MessageEvent` broadcast for outgoing messages) | The frontend already knows what it sent; echoing would be redundant |
| **Error handling on Telegram send** | Exceptions propagate and are logged; no retry | A production service would add retry logic with exponential back-off |
| **Authentication** | None | The assignment does not specify auth; WebSocket origins are restricted via CORS |
| **Concurrency model** | asyncio locks only | Sufficient for a single-process uvicorn worker; multiple workers would require a shared store |

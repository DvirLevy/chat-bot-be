# Chat Bridge — Backend

A production-quality FastAPI backend that bridges a React frontend (with
multiple named participants) and a single Telegram user via a WebSocket
connection and the Telegram Bot API.

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

The backend acts as a stateful relay between any number of named frontend
participants and a single Telegram user:

- A frontend client connects and sends a `join` event with a `username`.
- Only **one** username can be the *active participant* at a time. The first
  joiner is granted the turn (`turn_granted`); everyone else is told the
  session is `busy`.
- The active participant's messages are forwarded to the linked Telegram chat
  via the Bot API.
- Messages from the linked Telegram chat are forwarded to all connected
  frontend clients over WebSocket.
- The active participant is released when they send `end_chat`, disconnect,
  or go idle past `IDLE_TIMEOUT_SECONDS` — freeing the slot for the next
  participant.
- If the same username connects from a second tab/window, the older
  connection receives `session_replaced` and is closed.

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
│  (abstract,     │  │  WebSocket connection    │
│  in-memory and  │  │  manager                 │
│  SQL/Postgres)  │  │                          │
└─────────────────┘  └──────────────────────────┘
```

### Layers

| Layer | Path | Responsibility |
|-------|------|---------------|
| **API** | `app/api/` | FastAPI routes, WebSocket endpoint, input validation, response serialisation |
| **BL** | `app/bl/` | `ChatService` — chat orchestration, message routing, participant management, idle-timeout, concurrency protection |
| **DAL** | `app/dal/` | Repository abstractions (`MessageRepository`, `ChatStateRepository`, `UserRepository`); in-memory implementations (`app/dal/memory/`) and PostgreSQL/SQLAlchemy implementations (`app/dal/db/`) |
| **Infrastructure** | `app/infrastructure/` | `TelegramClient` (python-telegram-bot wrapper), `TelegramUpdateHandler` (callback bridge), `ConnectionManager` (per-username WebSocket connection tracking) |
| **Models** | `app/models/` | Shared Pydantic models (`Message`, `User`, WebSocket event envelopes, `TelegramUser`) |
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
│   │   │   ├── chat_state_repository.py
│   │   │   └── user_repository.py
│   │   ├── memory/
│   │   │   ├── in_memory_message_repository.py
│   │   │   ├── in_memory_chat_state_repository.py
│   │   │   └── in_memory_user_repository.py
│   │   └── db/
│   │       ├── base.py
│   │       ├── models.py          # SQLAlchemy ORM models (UserORM, MessageORM)
│   │       ├── session.py         # Async engine / session factory
│   │       ├── sql_message_repository.py
│   │       └── sql_user_repository.py
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
│   │   ├── user.py
│   │   ├── websocket_events.py
│   │   └── telegram_models.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   │
│   └── main.py
│
├── alembic/
│   ├── env.py
│   └── versions/                  # Database migrations
│
├── tests/
│   ├── conftest.py
│   ├── test_chat_service.py
│   ├── test_single_active_chat.py
│   ├── test_message_ordering.py
│   ├── test_message_repository.py
│   ├── test_user_repository.py
│   ├── test_connection_manager.py
│   ├── test_idle_timeout.py
│   └── test_websocket_protocol.py
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
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

### Persistence: PostgreSQL for Data, In-Memory for Session State

Messages and user/participant records are durable and survive a restart, so
they are persisted in **PostgreSQL** via SQLAlchemy's async ORM
(`SqlMessageRepository`, `SqlUserRepository`, schema in `app/dal/db/models.py`,
migrations in `alembic/`).

The active-session bookkeeping (which username currently holds the turn, the
global sequence counter, and the last-activity timestamp) is intentionally
**session-scoped and ephemeral** — it is reset on restart by design, so it
remains in `InMemoryChatStateRepository`.

The `MessageRepository`, `UserRepository`, and `ChatStateRepository`
abstractions mean swapping any of these stores requires only a new
implementation of the relevant interface — `ChatService` is untouched.

### Active Participant & Turn-Taking

Any number of frontend clients can connect, each identified by a `username`
sent in a `join` event. Only one username may be the *active participant*
(hold "the turn") at a time:

1. `ChatService.assign_active_user(username)` is protected by a
   double-checked locking pattern (`_assign_lock`):
   - Optimistic read (no lock) — returns immediately in the common case where
     an active participant is already set.
   - If the slot appears empty, acquire the lock, then re-read inside it to
     guard against the race where two coroutines both see `None` before
     either writes.
2. The first user to join (or to re-join while already active) is granted the
   turn (`turn_granted`); everyone else receives `busy`.
3. The Telegram chat ID is **linked** to the active username on that user's
   first incoming Telegram message (`UserRepository.set_chat_id`). Telegram
   messages from any other `chat_id` while a different user is active are
   dropped silently.
4. The turn is released when the active user sends `end_chat`, disconnects,
   or — via the idle-timeout checker — has been inactive for longer than
   `IDLE_TIMEOUT_SECONDS` (an `idle_timeout` event is broadcast when this
   happens).
5. If a username connects from a second WebSocket (e.g. another tab), the
   previous connection for that username receives `session_replaced` and is
   closed — only one live connection per username.

### Concurrency Safety

Python's asyncio event loop is single-threaded, but `await` points are
preemption points where another coroutine can run.  Any operation that spans
multiple `await` calls and must be atomic uses an `asyncio.Lock`:

- `ChatService._assign_lock`: atomic check-then-set for participant assignment.
- `InMemoryChatStateRepository._lock`: atomic increment of the sequence
  counter, and atomic reads/writes of the active username and last-activity
  timestamp.
- `InMemoryMessageRepository._lock`: serialised list mutations.
- `ConnectionManager._lock`: serialised mutations of the username → connection
  map.

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
5. From the frontend, join with a username to become the active participant.
   Send your bot a message from that Telegram account — the bot links your
   `chat_id` to your username on this first message, after which messages flow
   in both directions.

---

## Environment Setup

Configuration is sourced from a `.env` file in `backend/` (via
`pydantic-settings`). Required and optional variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_ENV` | `development` | Application environment, used for logging setup |
| `APP_HOST` | `0.0.0.0` | Host the server binds to |
| `APP_PORT` | `8000` | Port the server binds to |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | Allowed CORS origin for the frontend |
| `TELEGRAM_BOT_TOKEN` | *(required)* | Bot token from @BotFather |
| `DATABASE_URL` | `postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot` | SQLAlchemy async URL for PostgreSQL |
| `IDLE_TIMEOUT_SECONDS` | `300` | Seconds of inactivity before the active participant is released |

---

## Running Locally

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
# Create/edit .env with the variables listed above (TELEGRAM_BOT_TOKEN is required).

# 4. Start PostgreSQL (if not already running) and apply migrations
docker compose up -d db
alembic upgrade head

# 5. Start the server
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
# Create/edit .env with the variables listed above (TELEGRAM_BOT_TOKEN is required).
# When running via docker compose, DATABASE_URL is overridden to point at the
# "db" service (see docker-compose.yml).

# 2. Build and start (Postgres + backend)
docker compose up --build

# 3. Apply migrations (first run / after schema changes)
docker compose exec backend alembic upgrade head

# 4. Stop
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

Real-time bidirectional channel. Each connection represents one frontend
participant, identified by a `username`.

**On connect** the server immediately sends:
```json
{ "type": "status", "connected": true, "active_participant": false }
```
`active_participant` reflects whether *anyone* currently holds the turn.

**Frontend → Backend** (must be the first message — joins as `username`):
```json
{ "type": "join", "username": "alice" }
```
Response:
- If granted the turn: `HistoryEvent` followed by `TurnGrantedEvent`.
- If another user is active: `BusyEvent`.
- If `username` already has a live connection (e.g. another tab), that older
  connection receives `SessionReplacedEvent` and is closed.

**Frontend → Backend** (send a message; only honoured for the active user):
```json
{ "type": "send_message", "text": "Hello from the frontend" }
```
If `username` is not the active participant, the backend replies with
`BusyEvent` and the message is not sent. Empty/whitespace-only text is
rejected with `ErrorEvent`.

**Frontend → Backend** (voluntarily release the turn):
```json
{ "type": "end_chat" }
```
Releases the active slot if it is held by `username`.

**Backend → Frontend** (message history sent right after a successful join):
```json
{
  "type": "history",
  "messages": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "text": "Hello from Telegram",
      "direction": "incoming",
      "timestamp": "2024-01-15T10:30:00.000000+00:00",
      "sequence": 1,
      "username": "alice"
    }
  ]
}
```

**Backend → Frontend** (incoming Telegram message, broadcast to all clients):
```json
{
  "type": "message",
  "payload": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "text": "Hello from Telegram",
    "direction": "incoming",
    "timestamp": "2024-01-15T10:30:00.000000+00:00",
    "sequence": 2,
    "username": "alice"
  }
}
```

**Backend → Frontend** (turn granted to this connection):
```json
{ "type": "turn_granted" }
```

**Backend → Frontend** (another user currently holds the turn):
```json
{ "type": "busy" }
```

**Backend → Frontend** (the active participant was released for inactivity,
broadcast to all clients):
```json
{ "type": "idle_timeout", "username": "alice" }
```

**Backend → Frontend** (this connection was replaced by a newer connection
for the same username, then the socket is closed):
```json
{ "type": "session_replaced" }
```

**Backend → Frontend** (error — invalid message, or `send_message`/`end_chat`
sent before `join`):
```json
{ "type": "error", "message": "Invalid message format. Expected: ..." }
```

**On disconnect**: the connection is removed from `ConnectionManager`, and if
the disconnecting `username` was the active participant, the turn is released.

---

## Trade-offs and Assumptions

| Area | Decision | Trade-off |
|------|----------|-----------|
| **Message & user persistence** | PostgreSQL via SQLAlchemy async + Alembic migrations | Durable across restarts; adds an operational dependency (Postgres) |
| **Session state (active turn, sequence counter)** | In-memory only | Reset on restart by design — session-scoped, not user data |
| **Active participant** | One username at a time, first-to-join wins the turn; released on `end_chat`, disconnect, or idle timeout | Simple turn-taking model; no queueing for waiting users beyond a `busy` reply |
| **Telegram chat linking** | Bound to a username on that user's first Telegram message; messages from other chat IDs are dropped while a different user is active | Single Telegram account is shared sequentially across frontend usernames |
| **Multiple frontend clients** | One live connection per username (newer replaces older via `session_replaced`); incoming Telegram messages are broadcast to all connected clients | Suitable for a demo with a handful of named participants |
| **Outgoing message echo** | Not echoed back to frontend (no `MessageEvent` broadcast for outgoing messages) | The frontend already knows what it sent; echoing would be redundant |
| **Error handling on Telegram send** | Exceptions propagate and are logged; no retry | A production service would add retry logic with exponential back-off |
| **Authentication** | None — `username` is self-declared by the frontend | The assignment does not specify auth; WebSocket origins are restricted via CORS |
| **Concurrency model** | asyncio locks only | Sufficient for a single-process uvicorn worker; multiple workers would require a shared store for session state |

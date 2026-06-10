# CLAUDE.md — Chat Bridge Backend

This document is the authoritative reference for understanding, extending, and
maintaining this codebase.  Read it before making any changes.

---

## Project Architecture

The backend is a **FastAPI** application that bridges a React frontend (via
WebSocket) and a single Telegram user (via the Telegram Bot API).

```
React Frontend ──WebSocket──► FastAPI ──Bot API──► Telegram User
```

The application follows a **strict layered architecture**.  Each layer has a
clearly defined responsibility and must only import from layers at its own level
or below.

```
API  →  BL  →  DAL
              Infrastructure (same level as DAL; BL uses it, not the other way)
```

---

## Layer Responsibilities

### `app/api/`  — API Layer

- FastAPI route definitions only.
- Accept HTTP / WebSocket requests, validate inputs (via Pydantic), delegate to
  the BL layer, serialise responses.
- **Must not** contain any business logic.
- **Must not** import from `app/dal/` or `app/infrastructure/` directly.
- Access shared services via `websocket.app.state` / `request.app.state`.

### `app/bl/`  — Business Logic Layer

- All orchestration lives here (`ChatService`).
- Makes decisions: who is the active participant, which messages are stored,
  what gets forwarded where.
- **Must not** contain HTTP-specific code (no `Request`, no `WebSocket`).
- Depends on repository interfaces (abstract classes), not concrete implementations.
- Depends on `TelegramClient` and `ConnectionManager` via constructor injection.

### `app/dal/`  — Data Access Layer

Two sub-packages:

- `repositories/` — Abstract base classes (`MessageRepository`,
  `ChatStateRepository`).  These define the contract; no implementation.
- `memory/` — In-memory implementations.  Swapping these (e.g. for a Redis
  backend) must not require changes to `app/bl/`.

### `app/infrastructure/`  — Infrastructure Layer

- `telegram/` — Wraps `python-telegram-bot`.  The rest of the app must never
  import from `telegram.*` directly.
- `websocket/` — `ConnectionManager` owns the set of active WebSocket
  connections and the broadcast primitive.

### `app/models/`  — Shared Models

- `message.py` — `Message` is the canonical DTO used in every layer.
- `websocket_events.py` — Envelope types for the WebSocket protocol.
- `telegram_models.py` — Lightweight representations of Telegram entities.

### `app/core/`  — Application Infrastructure

- `config.py` — `pydantic-settings` `Settings` class.  All configuration comes
  from environment variables (via `.env`).  **Never hard-code secrets.**
- `logging.py` — Central logging initialisation.  All loggers must be obtained
  via `logging.getLogger("chatbot.<module>")`.

### `app/helpers/`  — Pure Utilities

- `id_helper.py` — UUID generation.
- `time_helper.py` — UTC timestamp formatting.
- Add a helper only when the same pure function is needed in multiple places.
  Avoid creating helpers for single-use logic.

---

## Folder Responsibilities

```
app/api/routes/health.py      GET /health — liveness endpoint
app/api/routes/websocket.py   WS /ws     — frontend real-time channel
app/bl/chat_service.py        All business logic
app/dal/repositories/         Abstract repository contracts
app/dal/memory/               In-memory implementations
app/infrastructure/telegram/  Telegram bot wrapper + callback bridge
app/infrastructure/websocket/ Connection set management + broadcast
app/models/                   Pydantic DTOs shared across layers
app/core/config.py            Environment-sourced settings (pydantic-settings)
app/core/logging.py           Logging bootstrap
app/helpers/                  Stateless utility functions
app/main.py                   Dependency wiring, lifespan, CORS middleware
tests/                        pytest-asyncio test suite
```

---

## Naming Conventions

| Construct | Convention | Example |
|-----------|-----------|---------|
| Files | `snake_case` | `chat_service.py` |
| Classes | `PascalCase` | `ChatService` |
| Methods / functions | `snake_case` | `handle_telegram_message` |
| Constants | `UPPER_SNAKE_CASE` | `REJECTED_MESSAGE` |
| Pydantic models | `PascalCase` | `Message`, `SendMessageEvent` |
| Abstract base classes | `PascalCase` with no suffix | `MessageRepository` |
| In-memory implementations | `InMemory` prefix | `InMemoryMessageRepository` |
| Loggers | `chatbot.<layer>` | `logging.getLogger("chatbot.service")` |

---

## Coding Standards

- **Type hints everywhere** — all function signatures, all class attributes.
- **Pydantic models** for all data crossing layer boundaries.
- **`async`/`await`** for all I/O-bound operations.
- **SOLID principles** — prefer small, focused classes; depend on abstractions.
- **Thin routes** — no logic in route handlers; call `chat_service.*` and return.
- **Readable over clever** — prefer clarity; avoid metaprogramming and
  over-abstraction.

---

## State Management Rules

1. **No database.** All state lives in the in-memory repositories.
2. **All mutable shared state lives in the DAL or Infrastructure layer**, never
   in module-level variables outside those layers.
3. **Repository abstractions are the single source of truth** for any piece of
   state.  Business logic must read and write through the repository interface,
   never through a concrete implementation's private fields.
4. **State is session-scoped.**  It is intentionally lost on server restart.
5. **Adding persistence** later requires only new repository implementations;
   `ChatService` must not change.

---

## WebSocket Rules

1. The WebSocket endpoint lives in `app/api/routes/websocket.py`.
2. All connection tracking is delegated to `ConnectionManager`.  The route must
   not hold references to `WebSocket` objects.
3. **Inbound envelope** (frontend → backend):
   ```json
   { "type": "send_message", "text": "..." }
   ```
4. **Outbound envelopes** (backend → frontend):
   ```json
   { "type": "message",  "payload": { ...Message } }
   { "type": "error",    "message": "..." }
   { "type": "status",   "connected": bool, "active_participant": bool }
   ```
5. Invalid messages must return an `ErrorEvent`, never crash the connection.
6. Disconnections must always call `connection_manager.disconnect(websocket)`.
7. Never `broadcast` from the API layer; always via `ChatService`.

---

## Telegram Integration Rules

1. All Telegram I/O must go through `TelegramClient`.  No other layer imports
   `telegram.*` (python-telegram-bot) directly.
2. `TelegramUpdateHandler` is the only class allowed to accept a
   `telegram.Update` argument; it immediately delegates to `ChatService`.
3. Call order: `add_message_handler(...)` → `start()`.  Never add handlers after
   the bot has started.
4. The bot uses long polling (`updater.start_polling`).  Do not switch to
   webhooks without also updating the Dockerfile and deployment config.
5. **Rejection message** for non-active participants is the constant
   `REJECTED_MESSAGE` defined in `chat_service.py`.  Do not duplicate it.

---

## Concurrency and Locking

All concurrency protection uses `asyncio.Lock`.  The strategy:

| Lock | Location | Guards |
|------|----------|--------|
| `_assign_lock` | `ChatService` | Atomic check-then-set of active participant |
| `_lock` | `InMemoryChatStateRepository` | Sequence counter increment |
| `_lock` | `InMemoryMessageRepository` | Message list mutations |
| `_lock` | `ConnectionManager` | WebSocket set mutations |

**Rules:**
- Never hold a lock across an `await` that calls another lock (risk of deadlock).
- Always snapshot data inside the lock and perform I/O outside it.
- Use the double-checked locking pattern where a re-read inside the lock
  is cheaper than always locking.

---

## Testing Standards

- Use `pytest-asyncio` with `asyncio_mode = auto` (configured in `pytest.ini`).
- Fixtures live in `tests/conftest.py`.
- Mock only I/O boundaries: `TelegramClient.send_message` and
  `ConnectionManager.broadcast`.  Use real in-memory repositories.
- Test names describe the observable behaviour, not the implementation:
  `test_second_sender_is_rejected` not `test_handle_telegram_message_rejected`.
- One assertion concept per test; multiple `assert` lines are fine when they
  all verify the same concept.

---

## Adding a New Feature (Checklist)

1. Define or extend a Pydantic model in `app/models/` if a new data shape is needed.
2. Add or extend the repository contract in `app/dal/repositories/` if new state is needed.
3. Implement the repository in `app/dal/memory/`.
4. Add the business logic to `ChatService` (or a new service class in `app/bl/`).
5. Expose it via a route in `app/api/routes/`.
6. Wire any new dependencies in `app/main.py`.
7. Write tests that cover the new behaviour end-to-end through `ChatService`.

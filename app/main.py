"""
Application entry point.

Dependency wiring
-----------------
All concrete implementations are instantiated here and stored on
``app.state``.  Routes access them via ``websocket.app.state`` or
``request.app.state`` so that no layer imports another layer's concrete type.

Lifecycle
---------
FastAPI's ``lifespan`` context manager starts the Telegram bot on startup and
gracefully shuts it down on application exit.  Using lifespan (rather than
deprecated ``on_event``) ensures proper async teardown even when the server
receives a SIGTERM.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.api.routes.websocket import router as ws_router
from app.bl.chat_service import ChatService
from app.core.config import settings
from app.core.logging import setup_logging
from app.dal.db.session import create_engine, create_session_factory
from app.dal.memory.in_memory_chat_state_repository import InMemoryChatStateRepository
from app.dal.memory.in_memory_message_repository import InMemoryMessageRepository
from app.infrastructure.telegram.telegram_client import TelegramClient
from app.infrastructure.telegram.telegram_update_handler import TelegramUpdateHandler
from app.infrastructure.websocket.connection_manager import ConnectionManager

# Configure logging as early as possible.
logger = setup_logging(settings.APP_ENV)

# ── Compose the dependency graph ──────────────────────────────────────────────

message_repo = InMemoryMessageRepository()
chat_state_repo = InMemoryChatStateRepository()
connection_manager = ConnectionManager()
telegram_client = TelegramClient(token=settings.TELEGRAM_BOT_TOKEN)

chat_service = ChatService(
    message_repo=message_repo,
    chat_state_repo=chat_state_repo,
    connection_manager=connection_manager,
    telegram_client=telegram_client,
)

update_handler = TelegramUpdateHandler(chat_service=chat_service)
telegram_client.add_message_handler(update_handler.handle_message)


# ── Application lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    logger.info("Starting application (env=%s)", settings.APP_ENV)

    # Database: one async engine for the app lifetime; share the session factory
    # via app.state so SQL repositories (BE-2, BE-3) can open sessions per call.
    db_engine = create_engine(settings.DATABASE_URL)
    app.state.db_engine = db_engine
    app.state.db_sessionmaker = create_session_factory(db_engine)
    logger.info("Database engine initialised")

    app.state.chat_service = chat_service
    app.state.connection_manager = connection_manager

    await telegram_client.start()
    logger.info("Application ready")

    yield  # Server is running

    # Shutdown
    logger.info("Shutting down application")
    await telegram_client.stop()
    await db_engine.dispose()
    logger.info("Application stopped")


# ── FastAPI app factory ───────────────────────────────────────────────────────

app = FastAPI(
    title="Chat Bridge API",
    description=(
        "Bridges a React frontend and a single Telegram user via "
        "WebSocket and the Telegram Bot API."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(ws_router)

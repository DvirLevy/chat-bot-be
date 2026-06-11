import asyncio
import contextlib
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
from app.dal.db.sql_message_repository import SqlMessageRepository
from app.dal.db.sql_user_repository import SqlUserRepository
from app.dal.memory.in_memory_chat_state_repository import InMemoryChatStateRepository
from app.infrastructure.telegram.telegram_client import TelegramClient
from app.infrastructure.telegram.telegram_update_handler import TelegramUpdateHandler
from app.infrastructure.websocket.connection_manager import ConnectionManager

logger = setup_logging(settings.APP_ENV)


chat_state_repo = InMemoryChatStateRepository()
connection_manager = ConnectionManager()
telegram_client = TelegramClient(token=settings.TELEGRAM_BOT_TOKEN)

db_engine = create_engine(settings.DATABASE_URL)
db_sessionmaker = create_session_factory(db_engine)
user_repo = SqlUserRepository(db_sessionmaker)
message_repo = SqlMessageRepository(db_sessionmaker)

chat_service = ChatService(
    message_repo=message_repo,
    chat_state_repo=chat_state_repo,
    connection_manager=connection_manager,
    telegram_client=telegram_client,
    user_repo=user_repo,
    idle_timeout_seconds=settings.IDLE_TIMEOUT_SECONDS,
)

update_handler = TelegramUpdateHandler(chat_service=chat_service)
telegram_client.add_message_handler(update_handler.handle_message)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting application (env=%s)", settings.APP_ENV)

    app.state.db_engine = db_engine
    app.state.db_sessionmaker = db_sessionmaker
    app.state.user_repo = user_repo
    logger.info("Database engine initialised")

    app.state.chat_service = chat_service
    app.state.connection_manager = connection_manager

    await telegram_client.start()

    idle_timeout_task = asyncio.create_task(chat_service.run_idle_timeout_checker())
    logger.info("Application ready")

    yield

    logger.info("Shutting down application")
    idle_timeout_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await idle_timeout_task
    await telegram_client.stop()
    await db_engine.dispose()
    logger.info("Application stopped")

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

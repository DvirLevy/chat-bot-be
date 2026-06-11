from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    FRONTEND_ORIGIN: str = "http://localhost:5173"
    TELEGRAM_BOT_TOKEN: str

    DATABASE_URL: str = (
        "postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot"
    )

    IDLE_TIMEOUT_SECONDS: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()

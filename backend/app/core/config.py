from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///../data/database/factwise.db"
    secret_key: str = "local-development-key-change-me"
    cookie_secure: bool = True
    cors_allowed_origins: str = "https://factwise-care.vercel.app,http://localhost:5173,http://127.0.0.1:5173"
    session_cookie: str = "factwise_session"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    App-wide configuration, loaded from environment variables or .env file.
    See .env.example for the variables this expects.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Postgres connection, e.g.
    # postgresql+psycopg2://attendance:attendance@localhost:5432/attendance
    database_url: str
    test_database_url: str
    timezone: str
    cors_origin: str = "http://localhost:8000"
    photos_dir: str = "photos"
    admin_session_hours: int = Field(12, ge=1, le=720)
    admin_cookie_secure: bool = False
    access_cookie_secure: bool = False
    whatsapp_bridge_url: str = "http://127.0.0.1:3001"
    whatsapp_bridge_token: str = ""


settings = Settings()  # pyright: ignore[reportCallIssue]

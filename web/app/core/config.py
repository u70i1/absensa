from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    App-wide configuration, loaded from environment variables or .env file.
    See .env.example for the variables this expects.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", hide_input_in_errors=True
    )

    # Postgres connection, e.g.
    # postgresql+psycopg2://attendance:attendance@localhost:5432/attendance
    database_url: str
    # Production does not need a test database. Tests must set their own URL.
    test_database_url: str = ""
    timezone: str = "Asia/Jakarta"
    cors_origin: str = "http://localhost:8000"
    photos_dir: str = "photos"
    admin_session_hours: int = Field(12, ge=1, le=720)
    admin_cookie_secure: bool = False
    access_cookie_secure: bool = False
    whatsapp_bridge_url: str = "http://127.0.0.1:3001"
    whatsapp_bridge_token: str = ""
    backups_dir: str = "backups"
    backup_encryption_key: SecretStr = SecretStr("")
    backup_times: str = "10:00,17:00"
    backup_keep_daily: int = Field(14, ge=1, le=365)
    backup_keep_weekly: int = Field(8, ge=0, le=104)
    backup_keep_monthly: int = Field(3, ge=0, le=120)
    backup_timeout_seconds: int = Field(3600, ge=60, le=86400)


settings = Settings()  # pyright: ignore[reportCallIssue]

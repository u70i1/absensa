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
    cors_origin: str = "http://localhost:5173"
    photos_dir: str = "photos"


settings = Settings() # pyright: ignore[reportCallIssue]

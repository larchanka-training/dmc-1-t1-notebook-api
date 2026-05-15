from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "MSD FastAPI Template"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"

    # Database settings
    database_url: str = ""

    # OAuth settings
    oauth_client_id: str = ""
    oauth_client_secret: str = ""

    # Token settings
    token_ttl_seconds: int = 86400
    session_ttl_seconds: int = 604800

    # Logging settings
    log_level: str = "DEBUG"
    log_level_console: str = "DEBUG"
    log_level_file: str = "INFO"
    log_file: Path = Path("logs/app.log")
    log_retention_days: int = 14

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()

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

    # JWT / Auth settings
    jwt_secret: str = "dev-jwt-secret-replace-in-production"
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 900      # 15 minutes
    session_ttl_seconds: int = 604800        # 7 days (refresh token)
    cookie_domain: str = ".notebook.com"

    # OpenTelemetry settings
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "dmc-1-t1-notebook-api"
    otel_logs_enabled: bool = True

    # Logging settings
    log_level: str = "DEBUG"
    log_level_console: str = "DEBUG"
    log_level_file: str = "INFO"
    log_file: Path = Path("logs/app.log")
    log_retention_days: int = 14
    enable_file_logging: bool = True

    @property
    def async_database_url(self) -> str:
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()

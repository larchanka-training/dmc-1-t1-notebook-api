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

    # Bedrock settings
    bedrock_model_id: str = "amazon.nova-lite-v1:0"
    bedrock_region: str = "eu-north-1"

    # AI rate limiting (per user, in-memory sliding window)
    ai_rate_limit_rpm: int = 10    # requests per minute
    ai_rate_limit_rpd: int = 100   # requests per day
    ai_max_prompt_chars: int = 32_000  # ~8K tokens; guards against oversized payloads

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

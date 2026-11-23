from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded and validated from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://tradealign:tradealign_pass@localhost:5432/tradealign_db",
        description="Async SQLAlchemy PostgreSQL connection string.",
    )

    # Gemini AI
    gemini_api_key: SecretStr = Field(..., description="Google Gemini API key.")
    gemini_model: str = Field(default="gemini-2.5-flash", description="Gemini model ID.")

    # BSE Scraper
    bse_poll_interval_minutes: int = Field(default=15, ge=1, le=1440)
    bse_request_timeout_seconds: int = Field(default=20, ge=5, le=120)

    # SMTP Email Delivery
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(..., description="SMTP login username/email.")
    smtp_password: SecretStr = Field(..., description="SMTP app password.")
    recipient_email: str = Field(..., description="Email address receiving the EOD digest.")


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of Settings."""
    return Settings()
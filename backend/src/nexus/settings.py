"""Configuration read from the environment (and `backend/.env` in development)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class FetchSettings(BaseSettings):
    """What the web fetcher needs: no database configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fetch_timeout_seconds: float = 30.0
    """Limit of each request to a publisher's site, redirects included one by one."""

    fetch_max_bytes: int = 5_000_000
    """Largest response body read from a publisher's site."""


class Settings(FetchSettings):
    database_url: SecretStr
    """Application URL: Neon's pooler in production."""

    database_url_direct: SecretStr | None = None
    """Direct URL, for Alembic and the Execution lock."""

    gemini_api_key: SecretStr | None = None
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_host: str | None = None


class MigrationSettings(BaseSettings):
    """What Alembic needs: the direct URL only."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url_direct: SecretStr


class ApiSettings(BaseSettings):
    """What the API needs before any adapter is built."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_allowed_origins: list[str] = ["http://localhost:3000"]

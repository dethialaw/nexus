"""Configuration read from the environment (and `backend/.env` in development)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: SecretStr
    """Application URL: Neon's pooler in production."""

    database_url_direct: SecretStr | None = None
    """Direct URL, for Alembic only."""

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

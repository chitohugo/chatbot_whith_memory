from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EnvironmentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)


class DatabaseSettings(EnvironmentSettings):
    url: str = Field(default="postgresql://postgres:postgres@localhost:5432/chatbot_db", validation_alias="DATABASE_URL")
    pool_size: int = Field(default=10, ge=1, le=100, validation_alias="DB_POOL_SIZE")


class OpenRouterSettings(EnvironmentSettings):
    api_key: SecretStr = Field(default="", validation_alias="OPENROUTER_API_KEY")
    base_url: str = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL")
    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="OPENROUTER_EMBEDDING_MODEL")
    model: str = Field(default="openrouter/free", validation_alias="OPENROUTER_MODEL")
    timeout: float = Field(default=30, gt=0, le=300, validation_alias="MODEL_TIMEOUT_SECONDS")


class APISettings(EnvironmentSettings):
    base_url: str = Field(default="http://localhost:8000", validation_alias="API_BASE_URL")
    timeout: float = Field(default=150, gt=0, validation_alias="API_TIMEOUT_SECONDS")


class UISettings(EnvironmentSettings):
    timezone: str = Field(default="America/Argentina/Buenos_Aires", validation_alias="UI_TIMEZONE")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value


class AuthSettings(EnvironmentSettings):
    secret_key: SecretStr = Field(default="", validation_alias="JWT_SECRET_KEY")
    algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM", pattern="^HS256$")
    access_token_expire_minutes: int = Field(default=60, ge=1, le=1440, validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
    login_attempts: int = Field(default=10, ge=1, validation_alias="LOGIN_ATTEMPTS_PER_MINUTE")


class FileSettings(EnvironmentSettings):
    root: Path = Field(default_factory=lambda: Path.home(), validation_alias="WORKSPACE_ROOT")
    scope: Literal["shared", "per_user"] = Field(default="shared", validation_alias="WORKSPACE_SCOPE")
    rules_file: Path | None = Field(default=Path(__file__).with_name("workspace_rules.json"), validation_alias="WORKSPACE_RULES_FILE")
    max_bytes: int = Field(default=100_000, ge=1024, le=10_000_000, validation_alias="MAX_FILE_BYTES")


class AgentSettings(EnvironmentSettings):
    max_steps: int = Field(default=6, ge=1, le=20, validation_alias="AGENT_MAX_STEPS")
    max_seconds: float = Field(default=120, gt=0, validation_alias="AGENT_MAX_SECONDS")
    context_tokens: int = Field(default=16_000, ge=2000, validation_alias="AGENT_CONTEXT_TOKENS")
    output_tokens: int = Field(default=2000, ge=128, validation_alias="AGENT_OUTPUT_TOKENS")
    memory_similarity: float = Field(default=.65, ge=0, le=1, validation_alias="MEMORY_MIN_SIMILARITY")


class Settings(EnvironmentSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    api: APISettings = Field(default_factory=APISettings)
    ui: UISettings = Field(default_factory=UISettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    files: FileSettings = Field(default_factory=FileSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)


settings = Settings()

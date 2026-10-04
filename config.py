from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/agent_db",
        validation_alias="DATABASE_URL",
    )


class OpenRouterSettings(BaseSettings):
    api_key: str = Field(..., validation_alias="OPENROUTER_API_KEY")
    base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "text-embedding-3-small"


class SessionSettings(BaseSettings):
    id: str = Field(default="default_session", validation_alias="SESSION_ID")
    user_id: str = Field(default="default_user", validation_alias="USER_ID")


class Settings(BaseSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


# Instancia global congelada para consumir en la app
settings = Settings()
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/chatbot_db",
        validation_alias="DATABASE_URL",
    )


class OpenRouterSettings(BaseSettings):
    api_key: str = Field(
        ...,
        validation_alias="OPENROUTER_API_KEY",
    )
    base_url: str = "https://openrouter.ai/api/v1"
    embedding_model: str = "text-embedding-3-small"


class SessionSettings(BaseSettings):
    id: str = Field(
        default="default_session",
        validation_alias="SESSION_ID",
    )
    user_id: str = Field(
        default="default_user",
        validation_alias="USER_ID",
    )


class APISettings(BaseSettings):
    base_url: str = Field(
        default="http://localhost:8000",
        validation_alias="API_BASE_URL",
    )


class AuthSettings(BaseSettings):
    secret_key: str = Field(
        ...,
        validation_alias="JWT_SECRET_KEY",
    )
    algorithm: str = Field(
        default="HS256",
        validation_alias="JWT_ALGORITHM",
    )
    access_token_expire_minutes: int = Field(
        default=60,
        validation_alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
    )


class Settings(BaseSettings):
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    api: APISettings = Field(default_factory=APISettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
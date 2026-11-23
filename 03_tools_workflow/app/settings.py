import logging
from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GeminiSettings(BaseModel):
    api_key: SecretStr | None = None
    model_name: str = "gemini-3.8-flash"
    fallback_model: str | None = None
    cache_client: bool = False


class AppSettings(BaseModel):
    name: str = "model-integrations"
    debug: bool = False
    environment: str = "development"


class Settings(BaseSettings):
    app: AppSettings = AppSettings()
    gemini: GeminiSettings = GeminiSettings()

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_nested_delimiter="__",
        extra="ignore",
    )


logger = logging.getLogger(__name__)


settings = Settings()

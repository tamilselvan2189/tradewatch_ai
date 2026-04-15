from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "TradeWatch AI"
    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    database_url: str = Field(alias="DATABASE_URL")
    redis_url: Optional[str] = Field(default=None, alias="REDIS_URL")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(alias="TELEGRAM_WEBHOOK_SECRET")
    telegram_webhook_path: str = Field(default="/telegram/webhook", alias="TELEGRAM_WEBHOOK_PATH")
    telegram_webhook_url: str = Field(alias="TELEGRAM_WEBHOOK_URL")

    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    groww_base_url: str = Field(default="https://api.groww.in", alias="GROWW_BASE_URL")
    groww_timeout_seconds: int = Field(default=20, alias="GROWW_TIMEOUT_SECONDS")
    groww_session_ttl_minutes: int = Field(default=60, alias="GROWW_SESSION_TTL_MINUTES")

    scheduler_timezone: str = Field(default="Asia/Kolkata", alias="SCHEDULER_TIMEZONE")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

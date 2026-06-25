from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "egarch.db"
    admin_api_key: str = "dev-admin-key"
    model_config = SettingsConfigDict(env_prefix="EGARCH_", env_file=".env")

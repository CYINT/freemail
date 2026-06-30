from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="FreeMail", validation_alias="FREEMAIL_APP_NAME")
    environment: str = Field(default="development", validation_alias="FREEMAIL_ENV")
    hostname: str = Field(default="freemail.kuzuryu.ai", validation_alias="FREEMAIL_HOSTNAME")
    release_version: str = Field(default="0.1.0-dev", validation_alias="FREEMAIL_RELEASE_VERSION")
    release_commit: str = Field(default="unknown", validation_alias="FREEMAIL_RELEASE_COMMIT")
    database_path: str = Field(default="data/freemail.sqlite", validation_alias="FREEMAIL_DB_PATH")
    admin_api_token: str | None = Field(default=None, validation_alias="FREEMAIL_ADMIN_API_TOKEN")
    vpn_only: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

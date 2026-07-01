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
    bootstrap_token: str | None = Field(default=None, validation_alias="FREEMAIL_BOOTSTRAP_TOKEN")
    session_secret: str | None = Field(default=None, validation_alias="FREEMAIL_SESSION_SECRET")
    session_ttl_seconds: int = Field(default=43200, validation_alias="FREEMAIL_SESSION_TTL_SECONDS")
    push_token_secret: str | None = Field(default=None, validation_alias="FREEMAIL_PUSH_TOKEN_SECRET")
    fcm_project_id: str | None = Field(default=None, validation_alias="FREEMAIL_FCM_PROJECT_ID")
    fcm_service_account_json: str | None = Field(default=None, validation_alias="FREEMAIL_FCM_SERVICE_ACCOUNT_JSON")
    apns_team_id: str | None = Field(default=None, validation_alias="FREEMAIL_APNS_TEAM_ID")
    apns_key_id: str | None = Field(default=None, validation_alias="FREEMAIL_APNS_KEY_ID")
    apns_private_key_pem: str | None = Field(default=None, validation_alias="FREEMAIL_APNS_PRIVATE_KEY_PEM")
    apns_bundle_id: str | None = Field(default=None, validation_alias="FREEMAIL_APNS_BUNDLE_ID")
    apns_use_sandbox: bool = Field(default=False, validation_alias="FREEMAIL_APNS_USE_SANDBOX")
    push_delivery_timeout_seconds: float = Field(default=10.0, validation_alias="FREEMAIL_PUSH_DELIVERY_TIMEOUT_SECONDS")
    mobile_ios_team_id: str | None = Field(default=None, validation_alias="FREEMAIL_MOBILE_IOS_TEAM_ID")
    mobile_ios_bundle_id: str = Field(
        default="technology.cyint.freemail",
        validation_alias="FREEMAIL_MOBILE_IOS_BUNDLE_ID",
    )
    mobile_android_package: str = Field(
        default="technology.cyint.freemail",
        validation_alias="FREEMAIL_MOBILE_ANDROID_PACKAGE",
    )
    mobile_android_sha256_cert_fingerprints: str | None = Field(
        default=None,
        validation_alias="FREEMAIL_MOBILE_ANDROID_SHA256_CERT_FINGERPRINTS",
    )
    max_attachment_bytes: int = Field(default=1_048_576, validation_alias="FREEMAIL_MAX_ATTACHMENT_BYTES")
    allowed_attachment_content_types: str = Field(
        default="text/plain,text/csv,application/pdf,image/png,image/jpeg",
        validation_alias="FREEMAIL_ALLOWED_ATTACHMENT_CONTENT_TYPES",
    )
    send_rate_window_seconds: int = Field(default=3600, validation_alias="FREEMAIL_SEND_RATE_WINDOW_SECONDS")
    send_rate_max_messages: int = Field(default=120, validation_alias="FREEMAIL_SEND_RATE_MAX_MESSAGES")
    send_rate_max_recipients: int = Field(default=500, validation_alias="FREEMAIL_SEND_RATE_MAX_RECIPIENTS")
    mail_core_host: str = Field(default="127.0.0.1", validation_alias="FREEMAIL_MAIL_CORE_HOST")
    smtp_port: int = Field(default=2525, validation_alias="FREEMAIL_SMTP_PORT")
    submission_port: int = Field(default=2465, validation_alias="FREEMAIL_SUBMISSION_PORT")
    imap_port: int = Field(default=2993, validation_alias="FREEMAIL_IMAP_PORT")
    jmap_port: int = Field(default=18092, validation_alias="FREEMAIL_JMAP_PORT")
    web_cors_origins: str = Field(
        default="http://127.0.0.1:18091,http://localhost:18091",
        validation_alias="FREEMAIL_WEB_CORS_ORIGINS",
    )
    vpn_only: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()

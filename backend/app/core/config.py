from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "mysql+pymysql://policy:policy@mysql:3306/policy"
    jwt_secret: str
    file_storage_root: str = "/runtime/files"
    schedule_timezone: str = "Asia/Shanghai"
    collection_cron_hour: int = 2
    collection_cron_minute: int = 0
    backup_root: str = "/runtime/backups"
    backup_cron_hour: int = Field(default=3, ge=0, le=23)
    backup_cron_minute: int = Field(default=30, ge=0, le=59)
    backup_retention_days: int = Field(default=7, ge=1)
    backup_job_timeout_seconds: int = Field(default=1800, ge=30)
    ai_adapter: str = "mock"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: int = 120
    deepseek_max_retries: int = 3
    deepseek_api_key: str | None = None
    wecom_webhook_url: SecretStr | None = None
    wecom_timeout_seconds: int = 10
    public_base_url: str | None = None


@lru_cache
def get_settings() -> Settings:
    # BaseSettings resolves this required value from the runtime environment.
    return Settings()  # type: ignore[call-arg]

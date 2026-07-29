from functools import lru_cache

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
    ai_adapter: str = "mock"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: int = 120
    deepseek_max_retries: int = 3
    deepseek_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    # BaseSettings resolves this required value from the runtime environment.
    return Settings()  # type: ignore[call-arg]

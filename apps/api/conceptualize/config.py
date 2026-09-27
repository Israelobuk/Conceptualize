from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = (
        "postgresql+psycopg://conceptualize:conceptualize@localhost:54329/conceptualize"
    )
    redis_url: str = "redis://127.0.0.1:63799/0"
    otel_exporter_otlp_endpoint: str = ""


settings = Settings()

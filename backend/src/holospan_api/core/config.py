from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HOLOSPAN_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Holospan API"
    version: str = "0.1.0"
    env: str = "development"
    deployment_mode: str = "docker-compose"
    database_url: str = "postgresql+asyncpg://holospan@localhost:5432/holospan"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    docs_enabled: bool = True
    max_request_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

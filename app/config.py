"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    postgres_user: str = "app"
    postgres_password: str = "app"
    postgres_db: str = "payments"
    postgres_host: str = "localhost"
    postgres_port: int = 5434

    provider_url: str = "http://localhost:8081"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

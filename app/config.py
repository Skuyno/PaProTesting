"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings read from environment variables."""
    postgres_user: str = "app"
    postgres_password: str = "app"
    postgres_db: str = "payments"
    postgres_host: str = "localhost"
    postgres_port: int = 5434

    provider_url: str = "http://localhost:8081"

    worker_poll_interval: float = 1.0
    worker_batch_size: int = 10
    worker_lease_seconds: int = 30
    worker_backoff_base: float = 0.5
    worker_backoff_cap: float = 15.0

    @property
    def database_url(self) -> str:
        """Return the assembled database url."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instances."""
    return Settings()

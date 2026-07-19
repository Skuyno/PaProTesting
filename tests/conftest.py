"""Shared fixtures for the payment service tests."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.database import Base
from app.dependencies import get_async_db
from app.main import app

TEST_DATABASE_URL = "postgresql+asyncpg://app:app@localhost:5434/payments_test"

# NullPool: no connection is kept alive between uses, so nothing here ever
# survives past the event loop it was created on.
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
test_session_maker = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
def create_models():
    """Create tables in the test database once per test run.

    The payments_test database itself is created by initdb/01-databases.sql
    when the postgres container initializes an empty volume.
    """

    async def _create():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())


@pytest.fixture
async def db(create_models):
    """Session maker for direct DB tests; truncates tables afterwards."""
    yield test_session_maker
    async with test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE operations, operation_events CASCADE"))


@pytest.fixture
async def client(db):
    """HTTP client wired to the app with the test database."""

    async def override_get_db():
        async with test_session_maker() as session:
            yield session

    app.dependency_overrides[get_async_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()

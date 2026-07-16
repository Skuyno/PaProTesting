"""FastAPI dependencies."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session.

    Yields:
        AsyncSession: Async database session.
    """
    async with async_session_maker() as session:
        yield session

"""Concurrency tests for the submit intent."""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import repository
from app.exceptions import OperationNotFoundError
from app.models import OperationEvent, OperationStatus
from app.schemas import OperationCreate


async def _create_operation(db, operation_id: str) -> None:
    """Create a bare operation directly through the repository."""
    async with db() as session:
        await repository.create_operation(
            session,
            OperationCreate(
                operation_id=operation_id, amount=Decimal("10.00"), currency="RUB"
            ),
        )


async def test_concurrent_submits_create_single_intent(db):
    """Out of many parallel submits exactly one creates the intent."""
    await _create_operation(db, "op-conc")

    async def one_submit() -> bool:
        async with db() as session:
            _, created = await repository.try_submit(session, "op-conc")
            return created

    results = await asyncio.gather(*(one_submit() for _ in range(10)))

    assert sum(results) == 1

    async with db() as session:
        op = await repository.get_operation(session, "op-conc")
        assert op.status == OperationStatus.PROCESSING
        events = (
            (
                await session.execute(
                    select(OperationEvent).where(
                        OperationEvent.operation_id == "op-conc",
                        OperationEvent.type == "SUBMITTED",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1


async def test_repeat_submit_returns_existing_state(db):
    """A second submit does not create a new intent and reports it."""
    await _create_operation(db, "op-repeat")
    async with db() as session:
        _, first = await repository.try_submit(session, "op-repeat")
    async with db() as session:
        op, second = await repository.try_submit(session, "op-repeat")

    assert first is True
    assert second is False
    assert op.status == OperationStatus.PROCESSING


async def test_submit_unknown_operation_raises(db):
    """Submitting a missing operation raises OperationNotFoundError."""
    async with db() as session:
        with pytest.raises(OperationNotFoundError):
            await repository.try_submit(session, "no-such-op")

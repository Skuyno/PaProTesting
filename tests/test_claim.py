"""Tests for claiming operations: leasing, exclusions and recovery."""

import asyncio
from decimal import Decimal

from app import repository
from app.schemas import OperationCreate


async def _submitted_operation(db, operation_id: str) -> None:
    """Create an operation and record its submit intent."""
    async with db() as session:
        await repository.create_operation(
            session,
            OperationCreate(
                operation_id=operation_id, amount=Decimal("10.00"), currency="RUB"
            ),
        )
    async with db() as session:
        await repository.try_submit(session, operation_id)


async def test_claim_leases_due_operation(db):
    """A due operation is claimed once and disappears until the lease ends."""
    await _submitted_operation(db, "op-claim")

    async with db() as session:
        first = await repository.claim_due_operations(session, 10, 30)
    async with db() as session:
        second = await repository.claim_due_operations(session, 10, 30)

    assert [op.operation_id for op in first] == ["op-claim"]
    assert first[0].attempt_count == 1
    assert second == []


async def test_concurrent_claims_do_not_share_operations(db):
    """Two parallel claims never return the same operation (SKIP LOCKED)."""
    for i in range(4):
        await _submitted_operation(db, f"op-race-{i}")

    async def one_claim() -> set[str]:
        async with db() as session:
            ops = await repository.claim_due_operations(session, 2, 30)
            return {op.operation_id for op in ops}

    left, right = await asyncio.gather(one_claim(), one_claim())

    assert left & right == set()
    assert len(left | right) == 4


async def test_claim_skips_operations_with_payment_id(db):
    """Operations whose payment is already accepted are not re-dispatched."""
    await _submitted_operation(db, "op-done")
    async with db() as session:
        await repository.save_provider_payment_id(session, "op-done", "pid-1")

    async with db() as session:
        claimed = await repository.claim_due_operations(session, 10, 30)

    assert claimed == []


async def test_claim_respects_retry_schedule(db):
    """An operation scheduled far in the future is not claimed yet."""
    await _submitted_operation(db, "op-later")
    async with db() as session:
        await repository.schedule_retry(session, "op-later", 60.0)

    async with db() as session:
        claimed = await repository.claim_due_operations(session, 10, 30)

    assert claimed == []


async def test_expired_lease_is_reclaimed(db):
    """An operation whose lease expired (dead worker) is claimed again."""
    await _submitted_operation(db, "op-dead")

    async with db() as session:
        first = await repository.claim_due_operations(session, 10, 0)
    async with db() as session:
        second = await repository.claim_due_operations(session, 10, 30)

    assert [op.operation_id for op in first] == ["op-dead"]
    assert [op.operation_id for op in second] == ["op-dead"]
    assert second[0].attempt_count == 2

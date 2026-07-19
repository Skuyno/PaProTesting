"""Data access layer for operations and their events."""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    OperationAlreadyExistsError,
    OperationNotFoundError,
    ReceiptConflictError,
)
from app.models import Operation, OperationEvent, OperationStatus
from app.schemas import OperationCreate, ReceiptIn


async def create_operation(db: AsyncSession, data: OperationCreate) -> Operation:
    """Create an operation with its initial CREATED event.

    Raises:
        OperationAlreadyExistsError: If operation_id is already taken.
    """
    op = Operation(
        operation_id=data.operation_id,
        amount=data.amount,
        currency=data.currency,
        description=data.description,
    )
    db.add(op)
    op_event = OperationEvent(
        operation_id=data.operation_id,
        event_id=1,
        type="CREATED",
        from_status=None,
        to_status=OperationStatus.CREATED,
        message="Operation created",
    )
    db.add(op_event)
    try:
        await db.commit()
    except IntegrityError as ex:
        await db.rollback()
        raise OperationAlreadyExistsError(data.operation_id) from ex
    return op


async def get_operation(db: AsyncSession, operation_id: str) -> Operation:
    """Get an operation by primary key.

    Raises:
        OperationNotFoundError: If no operation with this id exists.
    """
    op = await db.get(Operation, operation_id)
    if op is None:
        raise OperationNotFoundError(operation_id)
    return op


async def list_events(db: AsyncSession, operation_id: str) -> Sequence[OperationEvent]:
    """Get operation events by operation primary key."""
    await get_operation(db, operation_id)
    op_events = await db.execute(
        select(OperationEvent)
        .where(OperationEvent.operation_id == operation_id)
        .order_by(OperationEvent.event_id)
    )
    return op_events.scalars().all()


async def try_submit(db: AsyncSession, operation_id: str) -> tuple[Operation, bool]:
    """Atomically move an operation from CREATED to PROCESSING.

    Returns:
        The operation and whether this call created the submit intent
        (False means it was already PROCESSING or in a final state).

    Raises:
        OperationNotFoundError: If no operation with this id exists.
    """
    result = await db.execute(
        update(Operation)
        .where(
            Operation.operation_id == operation_id,
            Operation.status == OperationStatus.CREATED,
        )
        .values(status=OperationStatus.PROCESSING, next_attempt_at=func.now())
    )
    if result.rowcount == 1:
        next_event_id = await _next_event_id(db, operation_id)
        db.add(
            OperationEvent(
                operation_id=operation_id,
                event_id=next_event_id,
                type="SUBMITTED",
                from_status=OperationStatus.CREATED,
                to_status=OperationStatus.PROCESSING,
                message="Submission intent recorded",
            )
        )
        await db.commit()
    else:
        await db.rollback()
    op = await db.get(Operation, operation_id)
    if op is None:
        raise OperationNotFoundError(operation_id)
    return op, result.rowcount == 1


async def claim_due_operations(
    db: AsyncSession, batch_size: int, lease_seconds: int
) -> Sequence[Operation]:
    """Atomically claim up to batch_size due operations for dispatch.

    Claimed operations get next_attempt_at pushed lease_seconds into
    the future and attempt_count incremented, so other workers skip
    them until the lease expires.

    Returns:
        The claimed operations; empty if nothing is due.
    """
    result = await db.execute(
        select(Operation)
        .where(
            Operation.status == OperationStatus.PROCESSING,
            Operation.provider_payment_id.is_(None),
            Operation.next_attempt_at <= func.now(),
        )
        .order_by(Operation.next_attempt_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    operations = result.scalars().all()
    for op in operations:
        op.next_attempt_at = func.now() + timedelta(seconds=lease_seconds)
        op.attempt_count += 1
    await db.commit()
    return operations


async def save_provider_payment_id(
    db: AsyncSession, operation_id: str, provider_payment_id: str
) -> str | None:
    """Record the provider payment id unless one is already set.

    Returns:
        The id stored in the database after the call; differs from
        provider_payment_id if another writer linked the operation first.
    """
    result = await db.execute(
        update(Operation)
        .where(
            Operation.operation_id == operation_id,
            Operation.provider_payment_id.is_(None),
        )
        .values(provider_payment_id=provider_payment_id, next_attempt_at=None)
    )
    await db.commit()
    if result.rowcount == 1:
        return provider_payment_id
    return await db.scalar(
        select(Operation.provider_payment_id).where(
            Operation.operation_id == operation_id,
        )
    )


async def schedule_retry(
    db: AsyncSession, operation_id: str, delay_seconds: float
) -> bool:
    """Move the operation's next dispatch attempt into the future.

    Returns:
        False if the operation no longer needs dispatching because its
        provider payment id is already recorded, True otherwise.
    """
    result = await db.execute(
        update(Operation)
        .where(
            Operation.operation_id == operation_id,
            Operation.provider_payment_id.is_(None),
        )
        .values(next_attempt_at=func.now() + timedelta(seconds=delay_seconds))
    )
    await db.commit()
    return result.rowcount == 1


async def apply_receipt(db: AsyncSession, receipt: ReceiptIn) -> str:
    """Apply a provider receipt to its operation in one transaction.

    Returns:
        How the receipt was handled: "applied", "duplicate" or "ignored".

    Raises:
        OperationNotFoundError: If the operation does not exist.
        ReceiptConflictError: If the receipt contradicts the stored
            provider payment id.
    """
    result = await db.execute(
        select(Operation)
        .where(Operation.operation_id == receipt.operation_id)
        .with_for_update()
    )
    op = result.scalar_one_or_none()
    if op is None:
        raise OperationNotFoundError(receipt.operation_id)

    if op.provider_payment_id is None:
        op.provider_payment_id = receipt.provider_payment_id
    elif op.provider_payment_id != receipt.provider_payment_id:
        stored_pid = op.provider_payment_id
        await db.rollback()
        raise ReceiptConflictError(
            f"operation {receipt.operation_id}: receipt provider_payment_id "
            f"{receipt.provider_payment_id} does not match stored {stored_pid}"
        )


    new_status = OperationStatus(receipt.result)
    if op.status in (OperationStatus.COMPLETED, OperationStatus.REJECTED):
        if op.status == new_status:
            outcome = "duplicate"
        else:
            db.add(
                OperationEvent(
                    operation_id=op.operation_id,
                    event_id=await _next_event_id(db, op.operation_id),
                    type="RECEIPT_IGNORED",
                    from_status=op.status,
                    to_status=op.status,
                    message=f"Ignored late receipt with result {receipt.result}",
                )
            )
            outcome = "ignored"
    else:
        db.add(
            OperationEvent(
                operation_id=op.operation_id,
                event_id=await _next_event_id(db, op.operation_id),
                type=receipt.result,
                from_status=op.status,
                to_status=new_status,
                message=receipt.message,
            )
        )
        op.status = new_status
        op.next_attempt_at = None
        outcome = "applied"

    await db.commit()
    return outcome


async def _next_event_id(db: AsyncSession, operation_id: str) -> int:
    """Return the next event id. Caller must hold the operation row lock."""
    return await db.scalar(
        select(func.max(OperationEvent.event_id) + 1).where(
            OperationEvent.operation_id == operation_id
        )
    )

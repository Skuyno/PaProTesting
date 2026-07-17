"""Data access layer for operations and their events."""
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import OperationAlreadyExistsError
from app.models import Operation, OperationEvent, OperationStatus
from app.schemas import OperationCreate


async def create_operation(db: AsyncSession, data: OperationCreate) -> Operation:
    """Create an operation with its initial CREATED event.

    Raises:
        OperationAlreadyExistsErorr: If operation_id is already taken.
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


async def get_operation(db: AsyncSession, operation_id: str) -> Operation | None:
    """Get an operation by primary key."""
    op = await db.get(Operation, operation_id)
    return op


async def list_events(db: AsyncSession, operation_id: str) -> Sequence[OperationEvent]:
    """Get operation events by operation primary key."""
    op_events = await db.execute(
        select(OperationEvent)
        .where(OperationEvent.operation_id == operation_id)
        .order_by(OperationEvent.event_id)
    )
    return op_events.scalars().all()

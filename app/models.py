"""Models for the payment processing service."""

import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OperationStatus(enum.StrEnum):
    """Lifecycle states of a payment operation."""

    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


class Operation(Base):
    """Payment operation with its current state."""

    __tablename__ = "operations"

    operation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 2))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[OperationStatus] = mapped_column(
        String(16), default=OperationStatus.CREATED, index=True
    )
    provider_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    attempt_count: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationEvent(Base):
    """State transition history entry for an operation."""

    __tablename__ = "operation_events"

    operation_id: Mapped[str] = mapped_column(
        ForeignKey("operations.operation_id"), primary_key=True
    )
    event_id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    from_status: Mapped[OperationStatus | None] = mapped_column(String(16))
    to_status: Mapped[OperationStatus] = mapped_column(String(16))
    message: Mapped[str | None] = mapped_column(String(1024))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

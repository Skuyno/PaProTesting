"""Request and response schemas for the payment service API."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer
from pydantic.alias_generators import to_camel

from app.models import OperationStatus


class OperationCreate(BaseModel):
    """Payload for creating a payment operation."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    operation_id: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, max_digits=19, decimal_places=2)
    currency: Literal["RUB"]
    description: str | None = Field(default=None, max_length=1024)


class OperationResponse(BaseModel):
    """Operation state returned by the API."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )

    operation_id: str
    amount: Decimal
    currency: Literal["RUB"]
    description: str | None
    status: OperationStatus
    provider_payment_id: str | None

    @field_serializer("amount")
    def _amount_as_string(self, value: Decimal) -> str:
        return f"{value:.2f}"


class EventResponse(BaseModel):
    """Operation event state returned by the API."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, from_attributes=True
    )

    event_id: int
    type: str
    from_status: OperationStatus | None
    to_status: OperationStatus
    message: str | None
    occurred_at: datetime

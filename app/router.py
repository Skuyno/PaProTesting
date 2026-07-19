"""HTTP routes implementing the mandatory service API."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.dependencies import get_async_db
from app.schemas import EventResponse, OperationCreate, OperationResponse, ReceiptIn

router = APIRouter()


@router.get("/health")
async def health(db: Annotated[AsyncSession, Depends(get_async_db)]) -> JSONResponse:
    """Readiness probe: verifies the database is reachable."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503, content={"status": "degraded", "database": "down"}
        )
    return JSONResponse(status_code=200, content={"status": "ok", "database": "up"})


@router.post("/operations", response_model=OperationResponse, status_code=201)
async def create_operation(
    data: OperationCreate, db: Annotated[AsyncSession, Depends(get_async_db)]
) -> OperationResponse:
    """Create a payment operation in the CREATED state."""
    op = await repository.create_operation(db, data)
    return OperationResponse.model_validate(op)


@router.get("/operations/{operation_id}", response_model=OperationResponse)
async def get_operation(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> OperationResponse:
    """Return the current state of an operation."""
    op = await repository.get_operation(db, operation_id)
    return OperationResponse.model_validate(op)


@router.get("/operations/{operation_id}/events", response_model=list[EventResponse])
async def list_events(
    operation_id: str,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> list[EventResponse]:
    """Return the transition history of an operation."""
    op_events = await repository.list_events(db, operation_id)
    return [EventResponse.model_validate(e) for e in op_events]


@router.post("/operations/{operation_id}/submit", response_model=OperationResponse)
async def submit_operation(
    operation_id: str,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> OperationResponse:
    """Reliably schedule an operation for submission to the provider."""
    op, created = await repository.try_submit(db, operation_id)
    response.status_code = 202 if created else 200
    return OperationResponse.model_validate(op)


@router.post("/receipts", status_code=204)
async def receive_receipt(
    receipt: ReceiptIn,
    db: Annotated[AsyncSession, Depends(get_async_db)],
) -> None:
    """Accept a provider callback receipt."""
    await repository.apply_receipt(db, receipt)

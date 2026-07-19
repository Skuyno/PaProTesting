"""Tests for dispatching a single claimed operation to the provider."""

from decimal import Decimal

from app import repository
from app.exceptions import ProviderUnavailableError
from app.schemas import OperationCreate, ProviderPaymentResponse
from app.worker import process_operation


class FakeProvider:
    """Provider client stand-in with a programmable outcome."""

    def __init__(self, pid: str | None = None, error: Exception | None = None):
        """Store the pid to return or the error to raise."""
        self.pid = pid
        self.error = error

    async def create_payment(
        self, operation_id: str, amount: str, currency: str
    ) -> ProviderPaymentResponse:
        """Return the programmed response or raise the programmed error."""
        if self.error is not None:
            raise self.error
        return ProviderPaymentResponse(
            provider_payment_id=self.pid, status="ACCEPTED"
        )


async def _claimed_operation(db, operation_id: str):
    """Create, submit and claim one operation, returning the claimed row."""
    async with db() as session:
        await repository.create_operation(
            session,
            OperationCreate(
                operation_id=operation_id, amount=Decimal("10.00"), currency="RUB"
            ),
        )
    async with db() as session:
        await repository.try_submit(session, operation_id)
    async with db() as session:
        claimed = await repository.claim_due_operations(session, 1, 30)
    return claimed[0]


async def test_success_saves_payment_id(db, monkeypatch):
    """A 2xx provider response stores the pid and stops dispatching."""
    monkeypatch.setattr("app.worker.async_session_maker", db)
    op = await _claimed_operation(db, "op-ok")

    await process_operation(FakeProvider(pid="p-1"), op)

    async with db() as session:
        stored = await repository.get_operation(session, "op-ok")
        assert stored.provider_payment_id == "p-1"
        assert stored.next_attempt_at is None


async def test_unavailable_schedules_retry(db, monkeypatch):
    """A provider outage leaves no pid and re-schedules the operation."""
    monkeypatch.setattr("app.worker.async_session_maker", db)
    op = await _claimed_operation(db, "op-down")

    await process_operation(
        FakeProvider(error=ProviderUnavailableError("boom")), op
    )

    async with db() as session:
        stored = await repository.get_operation(session, "op-down")
        assert stored.provider_payment_id is None
        assert stored.next_attempt_at is not None


async def test_unexpected_error_is_swallowed(db, monkeypatch):
    """An unknown failure is logged, not raised, and changes nothing."""
    monkeypatch.setattr("app.worker.async_session_maker", db)
    op = await _claimed_operation(db, "op-bug")

    await process_operation(FakeProvider(error=ValueError("boom")), op)

    async with db() as session:
        stored = await repository.get_operation(session, "op-bug")
        assert stored.provider_payment_id is None

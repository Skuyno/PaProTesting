"""Background dispatcher that sends claimed operations to the provider."""

import asyncio
import contextlib
import logging
import random

from app import repository
from app.config import get_settings
from app.database import async_session_maker
from app.exceptions import ProviderUnavailableError
from app.metrics import dispatch_attempts
from app.models import Operation
from app.provider import ProviderClient

logger = logging.getLogger(__name__)


def backoff_delay(attempt: int) -> float:
    """Return the retry delay for the given attempt number.

    Grows exponentially, is capped by settings, and carries random
    jitter so retries from many operations do not synchronize.
    """
    return min(
        get_settings().worker_backoff_cap,
        get_settings().worker_backoff_base * 2**attempt,
    ) * random.uniform(0.5, 1.0)


async def process_operation(provider: ProviderClient, op: Operation) -> None:
    """Attempt to dispatch one claimed operation to the provider.

    Never raises: an expected provider outage reschedules the operation
    with backoff, anything unexpected is logged and left to the lease
    to re-queue. The final operation status is never touched here.
    """
    try:
        async with async_session_maker() as db:
            try:
                resp = await provider.create_payment(
                    op.operation_id, f"{op.amount:.2f}", op.currency
                )
            except ProviderUnavailableError as exc:
                dispatch_attempts.labels(result="unavailable").inc()
                delay = backoff_delay(op.attempt_count)
                scheduled = await repository.schedule_retry(db, op.operation_id, delay)
                if scheduled:
                    logger.warning(
                        "operation=%s attempt=%d provider unavailable (%s), "
                        "retry in %.1fs",
                        op.operation_id,
                        op.attempt_count,
                        exc,
                        delay,
                    )
            else:
                dispatch_attempts.labels(result="accepted").inc()
                stored = await repository.save_provider_payment_id(
                    db, op.operation_id, resp.provider_payment_id
                )
                if stored == resp.provider_payment_id:
                    logger.info(
                        "operation=%s attempt=%d provider accepted, "
                        "provider_payment_id=%s",
                        op.operation_id,
                        op.attempt_count,
                        resp.provider_payment_id,
                    )
                else:
                    logger.error(
                        "operation=%s attempt=%d provider_payment_id mismatch: "
                        "stored=%s received=%s",
                        op.operation_id,
                        op.attempt_count,
                        stored,
                        resp.provider_payment_id,
                    )
    except Exception:
        dispatch_attempts.labels(result="unexpected").inc()
        logger.exception(
            "operation=%s attempt=%d unexpected dispatch error",
            op.operation_id,
            op.attempt_count,
        )


async def run_worker(provider: ProviderClient, stop: asyncio.Event) -> None:
    """Poll the database and dispatch due operations until stop is set."""
    while not stop.is_set():
        try:
            async with async_session_maker() as db:
                ops = await repository.claim_due_operations(
                    db,
                    get_settings().worker_batch_size,
                    get_settings().worker_lease_seconds,
                )
            if ops:
                await asyncio.gather(*(process_operation(provider, op) for op in ops))
                continue
        except Exception:
            logger.exception("worker tick failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                stop.wait(), timeout=get_settings().worker_poll_interval
            )

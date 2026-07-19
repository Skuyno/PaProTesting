"""Tests for callback receipt processing rules."""

import asyncio


def _receipt(operation_id: str, pid: str, result: str) -> dict:
    """Build a receipt payload as the provider sends it."""
    return {
        "providerPaymentId": pid,
        "operationId": operation_id,
        "result": result,
        "message": f"Payment {result.lower()}",
        "occurredAt": "2026-07-19T12:00:00Z",
    }


async def _submitted_operation(client, operation_id: str) -> None:
    """Create and submit an operation through the API."""
    resp = await client.post(
        "/operations",
        json={"operationId": operation_id, "amount": "10.00", "currency": "RUB"},
    )
    assert resp.status_code == 201
    resp = await client.post(f"/operations/{operation_id}/submit")
    assert resp.status_code == 202


async def test_early_receipt_sets_pid_and_completes(client):
    """A receipt arriving before the provider response links and finalizes."""
    await _submitted_operation(client, "op-early")

    resp = await client.post("/receipts", json=_receipt("op-early", "p-1", "COMPLETED"))
    assert resp.status_code == 204

    op = (await client.get("/operations/op-early")).json()
    assert op["status"] == "COMPLETED"
    assert op["providerPaymentId"] == "p-1"

    events = (await client.get("/operations/op-early/events")).json()
    assert [e["type"] for e in events] == ["CREATED", "SUBMITTED", "COMPLETED"]


async def test_duplicate_receipt_adds_no_event(client):
    """The same receipt delivered twice does not create a second transition."""
    await _submitted_operation(client, "op-dup")
    receipt = _receipt("op-dup", "p-1", "REJECTED")

    assert (await client.post("/receipts", json=receipt)).status_code == 204
    before = (await client.get("/operations/op-dup/events")).json()
    assert (await client.post("/receipts", json=receipt)).status_code == 204
    after = (await client.get("/operations/op-dup/events")).json()

    assert len(after) == len(before)
    op = (await client.get("/operations/op-dup")).json()
    assert op["status"] == "REJECTED"


async def test_conflicting_receipt_is_ignored(client):
    """A late receipt with the opposite result never changes the final status."""
    await _submitted_operation(client, "op-conflict")

    assert (
        await client.post("/receipts", json=_receipt("op-conflict", "p-1", "COMPLETED"))
    ).status_code == 204
    assert (
        await client.post("/receipts", json=_receipt("op-conflict", "p-1", "REJECTED"))
    ).status_code == 204

    op = (await client.get("/operations/op-conflict")).json()
    assert op["status"] == "COMPLETED"

    events = (await client.get("/operations/op-conflict/events")).json()
    assert events[-1]["type"] == "RECEIPT_IGNORED"
    assert events[-1]["fromStatus"] == "COMPLETED"
    assert events[-1]["toStatus"] == "COMPLETED"


async def test_mismatched_pid_conflicts(client):
    """A receipt with a foreign payment id is rejected with 409."""
    await _submitted_operation(client, "op-mismatch")

    assert (
        await client.post("/receipts", json=_receipt("op-mismatch", "p-1", "COMPLETED"))
    ).status_code == 204
    resp = await client.post(
        "/receipts", json=_receipt("op-mismatch", "p-other", "COMPLETED")
    )

    assert resp.status_code == 409


async def test_receipt_for_unknown_operation_is_404(client):
    """A receipt about a nonexistent operation is permanently refused."""
    resp = await client.post("/receipts", json=_receipt("no-such", "p-1", "COMPLETED"))
    assert resp.status_code == 404


async def test_invalid_result_is_422(client):
    """A receipt with an unknown result value fails validation."""
    await _submitted_operation(client, "op-badresult")
    resp = await client.post("/receipts", json=_receipt("op-badresult", "p-1", "LOST"))
    assert resp.status_code == 422


async def test_concurrent_identical_receipts(client):
    """Parallel duplicate receipts produce one transition and no errors."""
    await _submitted_operation(client, "op-parallel")
    receipt = _receipt("op-parallel", "p-1", "COMPLETED")

    responses = await asyncio.gather(
        *(client.post("/receipts", json=receipt) for _ in range(5))
    )

    assert all(r.status_code == 204 for r in responses)
    events = (await client.get("/operations/op-parallel/events")).json()
    assert [e["type"] for e in events].count("COMPLETED") == 1

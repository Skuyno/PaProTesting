"""End-to-end API tests: full lifecycle and input validation."""


async def test_full_happy_path(client):
    """Create, submit, receive a receipt and observe the final state."""
    resp = await client.post(
        "/operations",
        json={
            "operationId": "op-e2e",
            "amount": "1000.00",
            "currency": "RUB",
            "description": "Оплата заказа",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "CREATED"
    assert body["providerPaymentId"] is None
    assert body["amount"] == "1000.00"

    assert (await client.post("/operations/op-e2e/submit")).status_code == 202
    assert (await client.post("/operations/op-e2e/submit")).status_code == 200

    resp = await client.post(
        "/receipts",
        json={
            "providerPaymentId": "p-e2e",
            "operationId": "op-e2e",
            "result": "COMPLETED",
            "message": "Payment completed",
            "occurredAt": "2026-07-19T12:00:00Z",
        },
    )
    assert resp.status_code == 204

    op = (await client.get("/operations/op-e2e")).json()
    assert op["status"] == "COMPLETED"
    assert op["providerPaymentId"] == "p-e2e"

    events = (await client.get("/operations/op-e2e/events")).json()
    assert [e["type"] for e in events] == ["CREATED", "SUBMITTED", "COMPLETED"]
    assert [e["eventId"] for e in events] == [1, 2, 3]


async def test_duplicate_create_conflicts(client):
    """Creating the same operationId twice returns 409."""
    payload = {"operationId": "op-twice", "amount": "5.00", "currency": "RUB"}
    assert (await client.post("/operations", json=payload)).status_code == 201
    assert (await client.post("/operations", json=payload)).status_code == 409


async def test_unknown_operation_is_404(client):
    """Reading a missing operation or its events returns 404."""
    assert (await client.get("/operations/absent")).status_code == 404
    assert (await client.get("/operations/absent/events")).status_code == 404


async def test_amount_validation(client):
    """Invalid amounts and currencies are rejected with 422."""
    cases = [
        {"operationId": "bad-1", "amount": "1.999", "currency": "RUB"},
        {"operationId": "bad-2", "amount": "-5.00", "currency": "RUB"},
        {"operationId": "bad-3", "amount": "0", "currency": "RUB"},
        {"operationId": "bad-4", "amount": "5.00", "currency": "USD"},
        {"amount": "5.00", "currency": "RUB"},
    ]
    for payload in cases:
        assert (await client.post("/operations", json=payload)).status_code == 422


async def test_health(client):
    """The readiness probe reports the database as reachable."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up"}

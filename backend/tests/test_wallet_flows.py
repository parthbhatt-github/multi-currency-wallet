from app.exchange import ExchangeService
from app.database import SessionLocal
from app.config import get_settings
from tests.conftest import signup


def auth(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def test_signup_login_profile(client):
    token = signup(client)
    profile = client.get("/me", headers=auth(token))
    assert profile.status_code == 200
    assert profile.json()["default_currency"] == "USD"

    updated = client.patch("/me", json={"default_currency": "EUR", "full_name": "Updated"}, headers=auth(token))
    assert updated.status_code == 200
    assert updated.json()["default_currency"] == "EUR"


def test_credit_debit_and_idempotency(client):
    token = signup(client)
    credit = client.post("/wallets/credit", json={"currency": "USD", "amount": "25.00"}, headers=auth(token, "credit-1"))
    assert credit.status_code == 201
    assert credit.json()["balance_after"] == "25.00"

    duplicate = client.post("/wallets/credit", json={"currency": "USD", "amount": "25.00"}, headers=auth(token, "credit-1"))
    assert duplicate.status_code == 201

    wallets = client.get("/wallets", headers=auth(token))
    assert wallets.json()[0]["balance"] == "25.00"

    debit = client.post("/wallets/debit", json={"currency": "USD", "amount": "5.00"}, headers=auth(token, "debit-1"))
    assert debit.status_code == 201
    assert debit.json()["balance_after"] == "20.00"


def test_cross_currency_transfer_records_trace(client):
    sender = signup(client, "sender@example.com")
    recipient = signup(client, "recipient@example.com", "EUR")

    db = SessionLocal()
    ExchangeService(db).seed_rates()
    db.close()

    client.post("/wallets/credit", json={"currency": "USD", "amount": "100.00"}, headers=auth(sender, "credit-2"))
    transfer = client.post(
        "/transfers",
        json={
            "recipient_email": "recipient@example.com",
            "source_currency": "USD",
            "target_currency": "EUR",
            "amount": "10.00",
            "description": "Dinner",
        },
        headers=auth(sender, "transfer-1"),
    )
    assert transfer.status_code == 201
    debit_tx = transfer.json()[0]
    assert debit_tx["type"] == "transfer_debit"
    assert debit_tx["rate_used"] is not None
    assert debit_tx["exchange_rate_id"] is not None

    sender_transactions = client.get("/transactions?limit=10", headers=auth(sender))
    assert sender_transactions.status_code == 200
    assert sender_transactions.json()["total"] == 2

    recipient_wallets = client.get("/wallets", headers=auth(recipient))
    assert recipient_wallets.json()[0]["currency"] == "EUR"
    assert recipient_wallets.json()[0]["balance_minor"] > 0


def test_insufficient_funds(client):
    token = signup(client)
    response = client.post("/wallets/debit", json={"currency": "USD", "amount": "1.00"}, headers=auth(token, "debit-2"))
    assert response.status_code == 409


def test_exchange_refresh_accepts_scheduler_token(client, monkeypatch):
    async def fake_refresh(self):
        return []

    get_settings().exchange_refresh_token = "scheduler-secret"
    monkeypatch.setattr(ExchangeService, "refresh", fake_refresh)

    forbidden = client.post("/exchange-rates/refresh")
    assert forbidden.status_code == 403

    refreshed = client.post("/exchange-rates/refresh", headers={"X-Exchange-Refresh-Token": "scheduler-secret"})
    assert refreshed.status_code == 200
    assert refreshed.json() == []

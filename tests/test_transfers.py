import uuid
from datetime import date


def create_transfer(client, **overrides):
    payload = {
        "from_account": "bank",
        "to_account": "cash",
        "amount": 100,
        "transfer_date": "2024-01-15",
    }
    payload.update(overrides)
    resp = client.post("/transfers", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_category(client, **overrides):
    payload = {"name": "Category", "type": "expense"}
    payload.update(overrides)
    resp = client.post("/categories", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_transaction(client, category_id, **overrides):
    payload = {
        "amount": 100,
        "category_id": category_id,
        "account_type": "cash",
        "transaction_date": "2024-01-15",
    }
    payload.update(overrides)
    resp = client.post("/transactions", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_transfer(db_session, user, **overrides):
    from src.models.enums import AccountType
    from src.models.transfer import Transfer

    fields = dict(
        id=uuid.uuid4(),
        user_id=user.id,
        from_account=AccountType.BANK,
        to_account=AccountType.CASH,
        amount=100,
        transfer_date=date(2024, 1, 1),
    )
    fields.update(overrides)
    transfer = Transfer(**fields)
    db_session.add(transfer)
    db_session.commit()
    return transfer


def test_create_bank_to_cash_withdrawal(client):
    body = create_transfer(
        client,
        from_account="bank",
        to_account="cash",
        amount=2500,
        transfer_date="2024-03-01",
        description="ATM withdrawal",
    )

    assert body["from_account"] == "bank"
    assert body["to_account"] == "cash"
    assert body["amount"] == 2500
    assert body["transfer_date"] == "2024-03-01"
    assert body["description"] == "ATM withdrawal"
    uuid.UUID(body["id"])
    uuid.UUID(body["user_id"])


def test_create_cash_to_bank_deposit(client):
    body = create_transfer(client, from_account="cash", to_account="bank", amount=900)

    assert body["from_account"] == "cash"
    assert body["to_account"] == "bank"
    assert body["amount"] == 900
    assert body["description"] is None
    uuid.UUID(body["id"])
    uuid.UUID(body["user_id"])


def test_list_transfers_shape(client):
    for day in ("01", "02", "03"):
        create_transfer(client, transfer_date=f"2024-01-{day}")

    resp = client.get("/transfers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_pages"] == 1
    # newest transfer_date first
    dates = [item["transfer_date"] for item in body["items"]]
    assert dates == ["2024-01-03", "2024-01-02", "2024-01-01"]


def test_list_transfers_pagination(client):
    for i in range(5):
        create_transfer(client, transfer_date=f"2024-01-{i + 1:02d}")

    resp = client.get("/transfers", params={"page": 2, "page_size": 2})

    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert body["total_pages"] == 3
    assert len(body["items"]) == 2


def test_list_transfers_filter_by_date_range(client):
    create_transfer(client, transfer_date="2024-01-01")
    create_transfer(client, transfer_date="2024-02-01")
    create_transfer(client, transfer_date="2024-03-01")

    resp = client.get("/transfers", params={"from": "2024-01-15", "to": "2024-02-15"})

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["transfer_date"] == "2024-02-01"


def test_list_transfers_is_user_scoped(client, db_session, other_user):
    _seed_transfer(db_session, other_user, amount=999)

    create_transfer(client, amount=100)

    resp = client.get("/transfers")

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == 100


def test_get_transfer(client):
    transfer = create_transfer(client)

    resp = client.get(f"/transfers/{transfer['id']}")

    assert resp.status_code == 200
    assert resp.json()["id"] == transfer["id"]


def test_get_transfer_not_found(client):
    resp = client.get(f"/transfers/{uuid.uuid4()}")

    assert resp.status_code == 404


def test_get_transfer_owned_by_other_user_not_found(client, db_session, other_user):
    other_transfer = _seed_transfer(db_session, other_user)

    resp = client.get(f"/transfers/{other_transfer.id}")

    assert resp.status_code == 404


def test_delete_transfer(client):
    transfer = create_transfer(client)

    resp = client.delete(f"/transfers/{transfer['id']}")

    assert resp.status_code == 204
    get_resp = client.get(f"/transfers/{transfer['id']}")
    assert get_resp.status_code == 404


def test_delete_transfer_not_found(client):
    resp = client.delete(f"/transfers/{uuid.uuid4()}")

    assert resp.status_code == 404


def test_create_transfer_same_account_rejected(client):
    resp = client.post(
        "/transfers",
        json={
            "from_account": "cash",
            "to_account": "cash",
            "amount": 100,
            "transfer_date": "2024-01-15",
        },
    )

    assert resp.status_code == 422


def test_create_transfer_zero_amount_rejected(client):
    resp = client.post(
        "/transfers",
        json={
            "from_account": "bank",
            "to_account": "cash",
            "amount": 0,
            "transfer_date": "2024-01-15",
        },
    )

    assert resp.status_code == 422


def test_create_transfer_negative_amount_rejected(client):
    resp = client.post(
        "/transfers",
        json={
            "from_account": "bank",
            "to_account": "cash",
            "amount": -5,
            "transfer_date": "2024-01-15",
        },
    )

    assert resp.status_code == 422


def test_transfer_does_not_affect_reports(client):
    income = _create_category(client, name="Salary", type="income")
    _create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")

    monthly_before = client.get("/reports/monthly").json()
    by_category_before = client.get("/reports/by-category").json()
    net_worth_before = client.get("/reports/net-worth").json()

    # sanity: the reports actually carry the transaction's values
    assert monthly_before == [{"month": "2024-01-01", "income": 1000, "expense": 0}]
    assert net_worth_before == [{"month": "2024-01-01", "net_worth": 1000}]

    create_transfer(client, from_account="bank", to_account="cash", amount=500, transfer_date="2024-01-10")

    assert client.get("/reports/monthly").json() == monthly_before
    assert client.get("/reports/by-category").json() == by_category_before
    assert client.get("/reports/net-worth").json() == net_worth_before

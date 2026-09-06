import uuid
from datetime import date, datetime


def test_list_opening_balances_empty_before_setup(client):
    resp = client.get("/opening-balances")

    assert resp.status_code == 200
    assert resp.json() == []


def test_put_opening_balance_creates_row(client):
    resp = client.put(
        "/opening-balances/cash",
        json={"amount": 5000, "as_of_date": "2024-01-01"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["amount"] == 5000
    assert body["as_of_date"] == "2024-01-01"
    assert body["account_type"] == "cash"
    uuid.UUID(body["id"])
    uuid.UUID(body["user_id"])


def test_put_opening_balance_upserts_existing_row(client):
    client.put("/opening-balances/cash", json={"amount": 5000, "as_of_date": "2024-01-01"})

    resp = client.put(
        "/opening-balances/cash",
        json={"amount": 7500, "as_of_date": "2024-02-01"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["amount"] == 7500
    assert body["as_of_date"] == "2024-02-01"
    assert datetime.fromisoformat(body["updated_at"]) >= datetime.fromisoformat(body["created_at"])

    list_body = client.get("/opening-balances").json()
    assert len(list_body) == 1
    assert list_body[0]["amount"] == 7500


def test_put_opening_balance_for_both_accounts(client):
    client.put("/opening-balances/cash", json={"amount": 100, "as_of_date": "2024-01-01"})
    client.put("/opening-balances/bank", json={"amount": 200, "as_of_date": "2024-01-01"})

    resp = client.get("/opening-balances")

    assert resp.status_code == 200
    body = resp.json()
    assert {row["account_type"] for row in body} == {"cash", "bank"}
    assert {row["amount"] for row in body} == {100, 200}


def test_opening_balances_are_user_scoped(client, db_session, other_user):
    from src.models.enums import AccountType
    from src.models.opening_balance import AccountOpeningBalance

    other_balance = AccountOpeningBalance(
        id=uuid.uuid4(),
        user_id=other_user.id,
        account_type=AccountType.CASH,
        amount=99999,
        as_of_date=date(2024, 1, 1),
    )
    db_session.add(other_balance)
    db_session.commit()

    list_body = client.get("/opening-balances").json()
    assert list_body == []

    put_body = client.put(
        "/opening-balances/cash",
        json={"amount": 100, "as_of_date": "2024-01-01"},
    ).json()
    assert put_body["amount"] == 100

    db_session.refresh(other_balance)
    assert other_balance.amount == 99999

    mine = client.get("/opening-balances").json()
    assert len(mine) == 1
    assert mine[0]["amount"] == 100


def test_put_opening_balance_invalid_account_type(client):
    resp = client.put(
        "/opening-balances/savings",
        json={"amount": 100, "as_of_date": "2024-01-01"},
    )

    assert resp.status_code == 422

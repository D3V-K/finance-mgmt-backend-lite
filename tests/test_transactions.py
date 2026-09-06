import uuid
from datetime import date


def create_category(client, **overrides):
    payload = {"name": "Category", "type": "expense"}
    payload.update(overrides)
    resp = client.post("/categories", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def create_transaction(client, category_id, **overrides):
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


def test_create_transaction(client):
    category = create_category(client)

    body = create_transaction(client, category["id"], amount=1234, description="Groceries")

    assert body["amount"] == 1234
    assert body["description"] == "Groceries"
    assert body["category_id"] == category["id"]
    assert body["account_type"] == "cash"
    assert body["transaction_date"] == "2024-01-15"
    uuid.UUID(body["id"])
    uuid.UUID(body["user_id"])


def test_create_transaction_persists_account_type(client):
    category = create_category(client)

    body = create_transaction(client, category["id"], account_type="bank")

    assert body["account_type"] == "bank"


def test_create_transaction_requires_account_type(client):
    category = create_category(client)

    resp = client.post(
        "/transactions",
        json={"amount": 100, "category_id": category["id"], "transaction_date": "2024-01-15"},
    )

    assert resp.status_code == 422


def test_create_transaction_invalid_category(client):
    resp = client.post(
        "/transactions",
        json={
            "amount": 100,
            "category_id": str(uuid.uuid4()),
            "account_type": "cash",
            "transaction_date": "2024-01-15",
        },
    )

    assert resp.status_code == 400


def test_create_transaction_category_owned_by_other_user(client, db_session, other_user):
    from src.models.category import Category, CategoryType

    other_category = Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.EXPENSE)
    db_session.add(other_category)
    db_session.commit()

    resp = client.post(
        "/transactions",
        json={
            "amount": 100,
            "category_id": str(other_category.id),
            "account_type": "cash",
            "transaction_date": "2024-01-15",
        },
    )

    assert resp.status_code == 400


def test_get_transaction(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"])

    resp = client.get(f"/transactions/{transaction['id']}")

    assert resp.status_code == 200
    assert resp.json()["id"] == transaction["id"]


def test_get_transaction_not_found(client):
    resp = client.get(f"/transactions/{uuid.uuid4()}")

    assert resp.status_code == 404


def test_get_transaction_owned_by_other_user_not_found(client, db_session, other_user):
    from src.models.category import Category, CategoryType
    from src.models.enums import AccountType
    from src.models.transaction import Transaction

    other_category = Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.EXPENSE)
    db_session.add(other_category)
    db_session.commit()
    other_transaction = Transaction(
        id=uuid.uuid4(),
        amount=100,
        category_id=other_category.id,
        account_type=AccountType.CASH,
        user_id=other_user.id,
        transaction_date=date(2024, 1, 1),
    )
    db_session.add(other_transaction)
    db_session.commit()

    resp = client.get(f"/transactions/{other_transaction.id}")

    assert resp.status_code == 404


def test_list_transactions(client):
    category = create_category(client)
    for day in ("01", "02", "03"):
        create_transaction(client, category["id"], transaction_date=f"2024-01-{day}")

    resp = client.get("/transactions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    # newest transaction_date first
    dates = [item["transaction_date"] for item in body["items"]]
    assert dates == ["2024-01-03", "2024-01-02", "2024-01-01"]


def test_list_transactions_pagination(client):
    category = create_category(client)
    for i in range(5):
        create_transaction(client, category["id"], transaction_date=f"2024-01-{i + 1:02d}")

    resp = client.get("/transactions", params={"page": 2, "page_size": 2})

    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["total_pages"] == 3
    assert len(body["items"]) == 2


def test_list_transactions_filter_by_date_range(client):
    category = create_category(client)
    create_transaction(client, category["id"], transaction_date="2024-01-01")
    create_transaction(client, category["id"], transaction_date="2024-02-01")
    create_transaction(client, category["id"], transaction_date="2024-03-01")

    resp = client.get("/transactions", params={"from": "2024-01-15", "to": "2024-02-15"})

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["transaction_date"] == "2024-02-01"


def test_list_transactions_filter_by_category(client):
    category_a = create_category(client, name="A")
    category_b = create_category(client, name="B")
    create_transaction(client, category_a["id"])
    create_transaction(client, category_b["id"])

    resp = client.get("/transactions", params={"category_id": category_a["id"]})

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["category_id"] == category_a["id"]


def test_list_transactions_is_user_scoped(client, db_session, other_user):
    from src.models.category import Category, CategoryType
    from src.models.enums import AccountType
    from src.models.transaction import Transaction

    other_category = Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.EXPENSE)
    db_session.add(other_category)
    db_session.commit()
    db_session.add(
        Transaction(
            id=uuid.uuid4(),
            amount=999,
            category_id=other_category.id,
            account_type=AccountType.CASH,
            user_id=other_user.id,
            transaction_date=date(2024, 1, 1),
        )
    )
    db_session.commit()

    category = create_category(client)
    create_transaction(client, category["id"])

    resp = client.get("/transactions")

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["amount"] == 100


def test_update_transaction(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"])

    resp = client.put(f"/transactions/{transaction['id']}", json={"amount": 500, "description": "Updated"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == 500
    assert body["description"] == "Updated"


def test_update_transaction_category(client):
    category_a = create_category(client, name="A")
    category_b = create_category(client, name="B")
    transaction = create_transaction(client, category_a["id"])

    resp = client.put(f"/transactions/{transaction['id']}", json={"category_id": category_b["id"]})

    assert resp.status_code == 200
    assert resp.json()["category_id"] == category_b["id"]


def test_update_transaction_account_type(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"], account_type="cash")

    resp = client.put(f"/transactions/{transaction['id']}", json={"account_type": "bank"})

    assert resp.status_code == 200
    assert resp.json()["account_type"] == "bank"


def test_update_transaction_rejects_explicit_null_account_type(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"])

    resp = client.put(f"/transactions/{transaction['id']}", json={"account_type": None})

    assert resp.status_code == 422


def test_update_transaction_invalid_category(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"])

    resp = client.put(f"/transactions/{transaction['id']}", json={"category_id": str(uuid.uuid4())})

    assert resp.status_code == 400


def test_update_transaction_rejects_explicit_null(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"])

    resp = client.put(f"/transactions/{transaction['id']}", json={"amount": None})

    assert resp.status_code == 422


def test_update_transaction_not_found(client):
    resp = client.put(f"/transactions/{uuid.uuid4()}", json={"amount": 500})

    assert resp.status_code == 404


def test_delete_transaction(client):
    category = create_category(client)
    transaction = create_transaction(client, category["id"])

    resp = client.delete(f"/transactions/{transaction['id']}")

    assert resp.status_code == 204
    get_resp = client.get(f"/transactions/{transaction['id']}")
    assert get_resp.status_code == 404


def test_delete_transaction_not_found(client):
    resp = client.delete(f"/transactions/{uuid.uuid4()}")

    assert resp.status_code == 404

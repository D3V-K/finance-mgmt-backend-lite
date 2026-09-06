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


def test_monthly_report_empty(client):
    resp = client.get("/reports/monthly")

    assert resp.status_code == 200
    assert resp.json() == []


def test_monthly_report_splits_income_and_expense(client):
    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, expense["id"], amount=300, transaction_date="2024-01-20")

    resp = client.get("/reports/monthly")

    assert resp.status_code == 200
    body = resp.json()
    assert body == [{"month": "2024-01-01", "income": 1000, "expense": 300}]


def test_monthly_report_groups_by_month_ordered(client):
    income = create_category(client, name="Salary", type="income")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-02-01")
    create_transaction(client, income["id"], amount=500, transaction_date="2024-01-01")

    resp = client.get("/reports/monthly")

    body = resp.json()
    assert [row["month"] for row in body] == ["2024-01-01", "2024-02-01"]
    assert body[0]["income"] == 500
    assert body[1]["income"] == 1000


def test_monthly_report_date_range_filter(client):
    income = create_category(client, name="Salary", type="income")
    create_transaction(client, income["id"], amount=100, transaction_date="2024-01-01")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-02-01")
    create_transaction(client, income["id"], amount=300, transaction_date="2024-03-01")

    resp = client.get("/reports/monthly", params={"from": "2024-02-01", "to": "2024-02-28"})

    body = resp.json()
    assert body == [{"month": "2024-02-01", "income": 200, "expense": 0}]


def test_monthly_report_is_user_scoped(client, db_session, other_user):
    from src.models.category import Category, CategoryType
    from src.models.enums import AccountType
    from src.models.transaction import Transaction

    other_category = Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.INCOME)
    db_session.add(other_category)
    db_session.commit()
    db_session.add(
        Transaction(
            id=uuid.uuid4(),
            amount=9999,
            category_id=other_category.id,
            account_type=AccountType.CASH,
            user_id=other_user.id,
            transaction_date=date(2024, 1, 1),
        )
    )
    db_session.commit()

    resp = client.get("/reports/monthly")

    assert resp.json() == []


def test_by_category_report_only_includes_expenses(client):
    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, income["id"], amount=1000)
    create_transaction(client, expense["id"], amount=200)

    resp = client.get("/reports/by-category")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["category_id"] == expense["id"]
    assert body[0]["category_name"] == "Food"
    assert body[0]["total"] == 200


def test_by_category_report_ordered_by_total_desc(client):
    small = create_category(client, name="Small", type="expense")
    big = create_category(client, name="Big", type="expense")
    create_transaction(client, small["id"], amount=50)
    create_transaction(client, big["id"], amount=500)

    resp = client.get("/reports/by-category")

    body = resp.json()
    assert [row["category_name"] for row in body] == ["Big", "Small"]


def test_by_category_report_date_range_filter(client):
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, expense["id"], amount=100, transaction_date="2024-01-01")
    create_transaction(client, expense["id"], amount=200, transaction_date="2024-06-01")

    resp = client.get("/reports/by-category", params={"from": "2024-05-01", "to": "2024-12-31"})

    body = resp.json()
    assert body == [{"category_id": expense["id"], "category_name": "Food", "total": 200}]


def test_net_worth_report_is_cumulative(client):
    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, expense["id"], amount=300, transaction_date="2024-02-10")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-03-01")

    resp = client.get("/reports/net-worth")

    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {"month": "2024-01-01", "net_worth": 1000},
        {"month": "2024-02-01", "net_worth": 700},
        {"month": "2024-03-01", "net_worth": 900},
    ]


def test_net_worth_report_date_filter_keeps_cumulative_total(client):
    income = create_category(client, name="Salary", type="income")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-03-01")

    resp = client.get("/reports/net-worth", params={"from": "2024-03-01"})

    body = resp.json()
    # net worth stays cumulative across all history, only the returned rows are windowed
    assert body == [{"month": "2024-03-01", "net_worth": 1200}]

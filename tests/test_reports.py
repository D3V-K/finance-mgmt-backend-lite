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


def put_opening_balance(client, account_type, amount, as_of_date="2024-01-01"):
    resp = client.put(
        f"/opening-balances/{account_type}",
        json={"amount": amount, "as_of_date": as_of_date},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


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


def test_balance_report_empty(client):
    resp = client.get("/reports/balance")

    assert resp.status_code == 200
    assert resp.json() == {"cash_balance": 0, "bank_balance": 0, "total_balance": 0}


def test_balance_report_opening_balances_only(client):
    put_opening_balance(client, "cash", 1000)
    put_opening_balance(client, "bank", 500)

    resp = client.get("/reports/balance")

    assert resp.status_code == 200
    assert resp.json() == {"cash_balance": 1000, "bank_balance": 500, "total_balance": 1500}


def test_balance_report_transactions_only(client):
    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    # cash: +1500 income, -400 expense -> 1100
    create_transaction(client, income["id"], amount=1500, account_type="cash")
    create_transaction(client, expense["id"], amount=400, account_type="cash")
    # bank: +2000 income, -750 expense -> 1250
    create_transaction(client, income["id"], amount=2000, account_type="bank")
    create_transaction(client, expense["id"], amount=750, account_type="bank")

    resp = client.get("/reports/balance")

    assert resp.status_code == 200
    assert resp.json() == {"cash_balance": 1100, "bank_balance": 1250, "total_balance": 2350}


def test_balance_report_transfers_only(client):
    create_transfer(client, from_account="bank", to_account="cash", amount=300)

    resp = client.get("/reports/balance")

    assert resp.status_code == 200
    assert resp.json() == {"cash_balance": 300, "bank_balance": -300, "total_balance": 0}


def test_balance_report_combination(client):
    put_opening_balance(client, "cash", 1000)
    put_opening_balance(client, "bank", 5000)

    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Rent", type="expense")

    create_transaction(client, income["id"], amount=2000, account_type="bank")   # bank +2000
    create_transaction(client, expense["id"], amount=250, account_type="cash")   # cash -250
    create_transaction(client, expense["id"], amount=1200, account_type="bank")  # bank -1200

    create_transfer(client, from_account="bank", to_account="cash", amount=800)  # cash +800, bank -800

    # cash = 1000 - 250 + 800         = 1550
    # bank = 5000 + 2000 - 1200 - 800 = 5000
    resp = client.get("/reports/balance")

    assert resp.status_code == 200
    assert resp.json() == {"cash_balance": 1550, "bank_balance": 5000, "total_balance": 6550}


def test_net_worth_report_seeded_with_opening_balances(client):
    put_opening_balance(client, "cash", 400)
    put_opening_balance(client, "bank", 600)

    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, expense["id"], amount=300, transaction_date="2024-02-10")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-03-01")

    resp = client.get("/reports/net-worth")

    assert resp.status_code == 200
    # same series as test_net_worth_report_is_cumulative (1000, 700, 900), offset by 400 + 600
    assert resp.json() == [
        {"month": "2024-01-01", "net_worth": 2000},
        {"month": "2024-02-01", "net_worth": 1700},
        {"month": "2024-03-01", "net_worth": 1900},
    ]


def test_net_worth_report_opening_balance_offsets_a_date_filtered_series(client):
    put_opening_balance(client, "cash", 300)
    put_opening_balance(client, "bank", 700)

    income = create_category(client, name="Salary", type="income")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-03-01")

    resp = client.get("/reports/net-worth", params={"from": "2024-03-01"})

    body = resp.json()
    # cumulative total (1200) still spans all history; opening total (1000) is a constant offset
    assert body == [{"month": "2024-03-01", "net_worth": 2200}]


def test_net_balance_alias_matches_net_worth(client):
    put_opening_balance(client, "cash", 250)
    put_opening_balance(client, "bank", 750)

    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, expense["id"], amount=300, transaction_date="2024-02-10")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-03-01")

    net_worth = client.get("/reports/net-worth")
    net_balance = client.get("/reports/net-balance")

    assert net_worth.status_code == 200
    assert net_balance.status_code == 200
    assert net_balance.json() == net_worth.json()
    assert net_balance.json() == [
        {"month": "2024-01-01", "net_worth": 2000},
        {"month": "2024-02-01", "net_worth": 1700},
        {"month": "2024-03-01", "net_worth": 1900},
    ]


def test_net_worth_report_no_transactions_returns_empty_even_with_opening_balances(client):
    put_opening_balance(client, "cash", 1000)
    put_opening_balance(client, "bank", 500)

    resp = client.get("/reports/net-worth")

    assert resp.status_code == 200
    # no month rows to anchor the running total to -> documented empty-series behavior
    assert resp.json() == []


def test_net_worth_report_opening_balance_is_user_scoped(client, db_session, other_user):
    from src.models.enums import AccountType
    from src.models.opening_balance import AccountOpeningBalance

    db_session.add(
        AccountOpeningBalance(
            id=uuid.uuid4(),
            user_id=other_user.id,
            account_type=AccountType.CASH,
            amount=99999,
            as_of_date=date(2024, 1, 1),
        )
    )
    db_session.commit()

    income = create_category(client, name="Salary", type="income")
    expense = create_category(client, name="Food", type="expense")
    create_transaction(client, income["id"], amount=1000, transaction_date="2024-01-05")
    create_transaction(client, expense["id"], amount=300, transaction_date="2024-02-10")
    create_transaction(client, income["id"], amount=200, transaction_date="2024-03-01")

    resp = client.get("/reports/net-worth")

    assert resp.status_code == 200
    # another user's opening balance must not shift this user's series
    assert resp.json() == [
        {"month": "2024-01-01", "net_worth": 1000},
        {"month": "2024-02-01", "net_worth": 700},
        {"month": "2024-03-01", "net_worth": 900},
    ]


def test_balance_report_is_user_scoped(client, db_session, other_user):
    from src.models.category import Category, CategoryType
    from src.models.enums import AccountType
    from src.models.opening_balance import AccountOpeningBalance
    from src.models.transaction import Transaction
    from src.models.transfer import Transfer

    db_session.add(
        AccountOpeningBalance(
            id=uuid.uuid4(),
            user_id=other_user.id,
            account_type=AccountType.CASH,
            amount=12345,
            as_of_date=date(2024, 1, 1),
        )
    )
    other_category = Category(
        id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.INCOME
    )
    db_session.add(other_category)
    db_session.commit()
    db_session.add(
        Transaction(
            id=uuid.uuid4(),
            amount=9999,
            category_id=other_category.id,
            account_type=AccountType.BANK,
            user_id=other_user.id,
            transaction_date=date(2024, 1, 1),
        )
    )
    db_session.add(
        Transfer(
            id=uuid.uuid4(),
            user_id=other_user.id,
            from_account=AccountType.BANK,
            to_account=AccountType.CASH,
            amount=777,
            transfer_date=date(2024, 1, 1),
        )
    )
    db_session.commit()

    resp = client.get("/reports/balance")

    assert resp.status_code == 200
    assert resp.json() == {"cash_balance": 0, "bank_balance": 0, "total_balance": 0}

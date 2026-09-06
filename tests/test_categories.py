import uuid


def create_category(client, **overrides):
    payload = {"name": "Category", "type": "expense"}
    payload.update(overrides)
    resp = client.post("/categories", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_category(client):
    body = create_category(client, name="Salary", type="income", color="#00ff00")

    assert body["name"] == "Salary"
    assert body["type"] == "income"
    assert body["color"] == "#00ff00"
    assert body["parent_id"] is None
    uuid.UUID(body["id"])
    uuid.UUID(body["user_id"])


def test_create_category_with_parent(client):
    parent = create_category(client, name="Food")
    child = create_category(client, name="Groceries", parent_id=parent["id"])

    assert child["parent_id"] == parent["id"]


def test_create_category_parent_not_found(client):
    resp = client.post(
        "/categories",
        json={"name": "Groceries", "type": "expense", "parent_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 400


def test_create_category_parent_owned_by_other_user(client, db_session, other_user):
    from src.models.category import Category, CategoryType

    other_category = Category(
        id=uuid.uuid4(), name="Other's category", user_id=other_user.id, type=CategoryType.EXPENSE
    )
    db_session.add(other_category)
    db_session.commit()

    resp = client.post(
        "/categories",
        json={"name": "Mine", "type": "expense", "parent_id": str(other_category.id)},
    )

    assert resp.status_code == 400


def test_list_categories(client):
    for i in range(3):
        create_category(client, name=f"Category {i}")

    resp = client.get("/categories")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total_pages"] == 1
    assert len(body["items"]) == 3


def test_list_categories_pagination(client):
    for i in range(5):
        create_category(client, name=f"Category {i}")

    resp = client.get("/categories", params={"page": 2, "page_size": 2})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["page_size"] == 2
    assert body["total_pages"] == 3
    assert len(body["items"]) == 2


def test_list_categories_is_user_scoped(client, db_session, other_user):
    from src.models.category import Category, CategoryType

    db_session.add(Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.EXPENSE))
    db_session.commit()
    create_category(client, name="Mine")

    resp = client.get("/categories")

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Mine"


def test_list_categories_tree(client):
    root = create_category(client, name="Food")
    child = create_category(client, name="Groceries", parent_id=root["id"])
    create_category(client, name="Other Root")

    resp = client.get("/categories/tree")

    assert resp.status_code == 200
    tree = resp.json()
    assert len(tree) == 2

    food = next(node for node in tree if node["id"] == root["id"])
    assert [c["id"] for c in food["children"]] == [child["id"]]


def test_update_category(client):
    category = create_category(client, name="Food")

    resp = client.put(f"/categories/{category['id']}", json={"name": "Groceries", "color": "#123456"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Groceries"
    assert body["color"] == "#123456"
    assert body["type"] == "expense"


def test_update_category_rejects_explicit_null(client):
    category = create_category(client, name="Food")

    resp = client.put(f"/categories/{category['id']}", json={"name": None})

    assert resp.status_code == 422


def test_update_category_cannot_be_own_parent(client):
    category = create_category(client, name="Food")

    resp = client.put(f"/categories/{category['id']}", json={"parent_id": category["id"]})

    assert resp.status_code == 400


def test_update_category_cannot_create_cycle(client):
    root = create_category(client, name="Food")
    child = create_category(client, name="Groceries", parent_id=root["id"])

    resp = client.put(f"/categories/{root['id']}", json={"parent_id": child["id"]})

    assert resp.status_code == 400


def test_update_category_parent_not_found(client):
    category = create_category(client, name="Food")

    resp = client.put(f"/categories/{category['id']}", json={"parent_id": str(uuid.uuid4())})

    assert resp.status_code == 400


def test_update_category_not_found(client):
    resp = client.put(f"/categories/{uuid.uuid4()}", json={"name": "Nope"})

    assert resp.status_code == 404


def test_update_category_owned_by_other_user_not_found(client, db_session, other_user):
    from src.models.category import Category, CategoryType

    other_category = Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.EXPENSE)
    db_session.add(other_category)
    db_session.commit()

    resp = client.put(f"/categories/{other_category.id}", json={"name": "Hijacked"})

    assert resp.status_code == 404


def test_delete_category(client):
    category = create_category(client, name="Food")

    resp = client.delete(f"/categories/{category['id']}")

    assert resp.status_code == 204
    list_resp = client.get("/categories")
    assert list_resp.json()["total"] == 0


def test_delete_category_not_found(client):
    resp = client.delete(f"/categories/{uuid.uuid4()}")

    assert resp.status_code == 404


def test_delete_category_owned_by_other_user_not_found(client, db_session, other_user):
    from src.models.category import Category, CategoryType

    other_category = Category(id=uuid.uuid4(), name="Other's", user_id=other_user.id, type=CategoryType.EXPENSE)
    db_session.add(other_category)
    db_session.commit()

    resp = client.delete(f"/categories/{other_category.id}")

    assert resp.status_code == 404


def test_delete_category_cascades_to_transactions(client):
    category = create_category(client, name="Food")
    tx_resp = client.post(
        "/transactions",
        json={
            "amount": 500,
            "category_id": category["id"],
            "account_type": "cash",
            "transaction_date": "2024-01-01",
        },
    )
    assert tx_resp.status_code == 201

    resp = client.delete(f"/categories/{category['id']}")

    assert resp.status_code == 204
    transactions = client.get("/transactions").json()
    assert transactions["total"] == 0

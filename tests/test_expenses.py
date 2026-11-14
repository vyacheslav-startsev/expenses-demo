from app import db


def add(client, amount, spent_on="2026-11-03", category="Продукты", note=""):
    return client.post(
        "/expenses",
        data={"amount": amount, "spent_on": spent_on, "category": category, "note": note},
        follow_redirects=False,
    )


def test_added_expense_counts_in_its_month(client):
    response = add(client, "1 254,90")
    assert response.status_code == 303
    assert response.headers["location"] == "/?month=2026-11"
    assert db.month_total("2026-11") == 125490
    assert db.month_total("2026-10") == 0


def test_accepts_amount_copied_from_page(client):
    response = add(client, "2\u00a0180\u00a0₽")
    assert response.status_code == 303
    assert db.month_total("2026-11") == 218000


def test_month_page_shows_total_and_categories(client):
    add(client, "1000", category="Продукты")
    add(client, "250,50", category="Кафе")
    page = client.get("/?month=2026-11").text
    assert "1 250,50 ₽" in page
    assert db.by_category("2026-11") == [("Продукты", 100000), ("Кафе", 25050)]


def test_rejects_bad_amount_and_unknown_category(client):
    assert add(client, "много").status_code == 400
    assert add(client, "100", category="Казино").status_code == 400
    assert db.month_total("2026-11") == 0


def test_delete_expense(client):
    add(client, "500")
    expense_id = db.list_month("2026-11")[0]["id"]
    client.post(f"/expenses/{expense_id}/delete", data={"month": "2026-11"})
    assert db.list_month("2026-11") == []

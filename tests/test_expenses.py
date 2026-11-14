import re

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


def test_bad_amount_shows_form_with_error_and_entered_values(client):
    response = add(client, "много", category="Кафе", note="обед")
    assert response.status_code == 400
    assert "text/html" in response.headers["content-type"]
    page = response.text
    assert "Не понимаю сумму: много" in page
    assert 'value="много"' in page
    assert 'value="обед"' in page
    assert 'value="2026-11-03"' in page
    assert "<option selected>Кафе</option>" in page
    assert "Ноябрь 2026" in page


def test_bad_date_shows_russian_error(client):
    response = add(client, "100", spent_on="вчера")
    assert response.status_code == 400
    assert "Укажите дату" in response.text
    assert 'value="100"' in response.text


def test_unknown_category_shows_error_on_page(client):
    response = add(client, "100", category="Казино")
    assert response.status_code == 400
    assert "Неизвестная категория" in response.text


def test_delete_expense(client):
    add(client, "500")
    expense_id = db.list_month("2026-11")[0]["id"]
    client.post(f"/expenses/{expense_id}/delete", data={"month": "2026-11"})
    assert db.list_month("2026-11") == []


def date_input(page):
    return re.search(r'<input name="spent_on"[^>]*>', page).group(0)


def test_fresh_form_marks_date_for_auto_refresh(client):
    page = client.get("/?month=2026-09").text
    assert "data-auto-today" in date_input(page)


def test_form_after_error_keeps_entered_date_without_auto_refresh(client):
    page = add(client, "много", spent_on="2026-09-03").text
    assert 'value="2026-09-03"' in page
    assert "data-auto-today" not in date_input(page)

from html.parser import HTMLParser
from pathlib import Path

import pytest

from app import db

SAMPLE = Path("samples/statement-2026-11.csv").read_bytes()


class FormFields(HTMLParser):
    """Поля, которые браузер отправил бы из формы сохранения импорта."""

    def __init__(self):
        super().__init__()
        self.fields: list[tuple[str, str]] = []
        self._in_save_form = False
        self._select: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self._in_save_form = a.get("action") == "/import/save"
        if not self._in_save_form:
            return
        if tag == "input" and "name" in a:
            if a.get("type") == "checkbox" and "checked" not in a:
                return
            self.fields.append((a["name"], a.get("value", "")))
        elif tag == "select":
            self._select = a["name"]
        elif tag == "option" and self._select and "selected" in a:
            self.fields.append((self._select, a.get("value", "")))

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
        elif tag == "form":
            self._in_save_form = False


def upload(client, data: bytes):
    return client.post("/import", files={"statement": ("s.csv", data, "text/csv")})


def preview_fields(client) -> list[tuple[str, str]]:
    page = upload(client, SAMPLE)
    assert page.status_code == 200
    parser = FormFields()
    parser.feed(page.text)
    return parser.fields


def save(client, fields):
    return client.post("/import/save", data=_as_form(fields), follow_redirects=False)


def _as_form(fields):
    form: dict[str, list[str]] = {}
    for name, value in fields:
        form.setdefault(name, []).append(value)
    return form


def replace(fields, name, value):
    return [(n, value if n == name else v) for n, v in fields]


def test_preview_lists_rows(client):
    page = upload(client, SAMPLE)
    assert page.status_code == 200
    for text in ["Перекрёсток", "2\xa0318,60\xa0₽", "не прошла", "зачисление", "Сохранить"]:
        assert text in page.text
    assert db.month_total("2026-11") == 0


def test_save_selected(client):
    fields = preview_fields(client)
    assert dict(fields)["count"] == "22"
    assert len([n for n, _ in fields if n == "pick"]) == 20
    response = save(client, fields)
    assert response.status_code == 303
    assert response.headers["location"] == "/?month=2026-11"
    assert db.month_total("2026-11") == 3040975
    assert dict(db.by_category("2026-11"))["Продукты"] == 1295875


def test_category_override_and_unpick(client):
    fields = preview_fields(client)
    fields = replace(fields, "category_0", "Развлечения")  # Перекрёсток 2 318,60
    fields = [(n, v) for n, v in fields if (n, v) != ("pick", "1")]  # Метро 62,00
    save(client, fields)
    assert db.month_total("2026-11") == 3040975 - 6200
    notes = {(e["note"], e["category"]) for e in db.list_month("2026-11")}
    assert ("Перекрёсток", "Развлечения") in notes
    assert all(e["spent_on"] != "2026-11-11" or e["note"] != "Метро"
               for e in db.list_month("2026-11"))


def test_double_save_no_duplicates(client):
    fields = preview_fields(client)
    save(client, fields)
    save(client, fields)
    assert db.month_total("2026-11") == 3040975


def test_save_nothing_redirects_home(client):
    fields = [(n, v) for n, v in preview_fields(client) if n != "pick"]
    response = save(client, fields)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert db.month_total("2026-11") == 0


def test_reupload_marks_known(client):
    save(client, preview_fields(client))
    page = upload(client, SAMPLE)
    assert page.text.count("уже загружено") == 20


@pytest.mark.parametrize(
    "name, value",
    [
        ("category_0", "Казино"),
        ("amount_kop_0", "abc"),
        ("amount_kop_0", "0"),
        ("spent_on_0", "2026-13-01"),
    ],
)
def test_save_rejects_tampered(client, name, value):
    fields = replace(preview_fields(client), name, value)
    assert save(client, fields).status_code == 400
    assert db.month_total("2026-11") == 0


@pytest.mark.parametrize(
    "data, message",
    [
        (SAMPLE.decode("utf-8").encode("cp1251"), "UTF-8"),
        (b"", "Файл пуст"),
        (SAMPLE.decode("utf-8").replace("Статус", "Состояние", 1).encode("utf-8"), "«Статус»"),
    ],
)
def test_upload_errors(client, data, message):
    response = upload(client, data)
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_index_has_upload_form(client):
    page = client.get("/?month=2026-11").text
    assert 'action="/import"' in page
    assert 'enctype="multipart/form-data"' in page

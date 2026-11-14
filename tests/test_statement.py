from pathlib import Path

import pytest

from app.statement import StatementError, StatementRow, parse_statement

SAMPLE = Path("samples/statement-2026-11.csv").read_bytes()
SAMPLE_TEXT = SAMPLE.decode("utf-8")
HEADER = SAMPLE_TEXT.splitlines()[0]


def one_row(status="OK", amount="-100,00", currency="RUB", category="Супермаркеты",
            when="09.11.2026 13:05:12", note="Магазин"):
    line = f"{when};09.11.2026;*4417;{status};{amount};{currency};{category};5411;{note}"
    return f"{HEADER}\n{line}\n".encode("utf-8")


def by_note(rows, note):
    return [r for r in rows if r.note == note]


def test_parses_sample():
    rows = parse_statement(SAMPLE)
    assert len(rows) == 24
    assert len([r for r in rows if r.skip_reason is None]) == 22
    picked = [r for r in rows if r.selected]
    assert len(picked) == 20
    assert sum(r.amount_kop for r in picked) == 3040975


def test_first_row_fields():
    assert parse_statement(SAMPLE)[0] == StatementRow(
        ref="2026-11-11T19:42:10|*4417|-231860|Перекрёсток",
        spent_on="2026-11-11",
        amount_kop=231860,
        note="Перекрёсток",
        bank_category="Супермаркеты",
        category="Продукты",
        selected=True,
        skip_reason=None,
    )


def test_skip_reasons():
    rows = parse_statement(SAMPLE)
    (failed,) = by_note(rows, "Магазин Спортмастерская")
    assert (failed.skip_reason, failed.selected) == ("не прошла", False)
    (salary,) = by_note(rows, "Зачисление заработной платы")
    assert (salary.skip_reason, salary.selected) == ("зачисление", False)
    (usd,) = parse_statement(one_row(currency="USD"))
    assert (usd.skip_reason, usd.selected) == ("не рубли", False)


def test_transfers_unchecked():
    transfers = by_note(parse_statement(SAMPLE), "Перевод между своими счетами")
    assert len(transfers) == 2
    for row in transfers:
        assert row.skip_reason is None
        assert row.selected is False
        assert row.category == "Другое"


def test_same_coffee_twice_kept():
    coffee = [r for r in by_note(parse_statement(SAMPLE), "Кофейня Зерно")
              if r.spent_on == "2026-11-09"]
    assert [r.amount_kop for r in coffee] == [28000, 28000]
    assert coffee[0].ref != coffee[1].ref


@pytest.mark.parametrize(
    "bank, app",
    [
        ("Супермаркеты", "Продукты"),
        ("Рестораны", "Кафе"),
        ("Фастфуд", "Кафе"),
        ("Транспорт", "Транспорт"),
        ("Такси", "Транспорт"),
        ("Коммунальные услуги", "Дом"),
        ("Связь", "Дом"),
        ("Аптеки", "Здоровье"),
        ("Кино", "Развлечения"),
        ("Цифровые товары", "Развлечения"),
        ("Одежда и обувь", "Другое"),
        ("Неизвестное", "Другое"),
    ],
)
def test_category_map(bank, app):
    (row,) = parse_statement(one_row(category=bank))
    assert row.bank_category == bank
    assert row.category == app


def test_bom_and_crlf():
    data = b"\xef\xbb\xbf" + SAMPLE_TEXT.replace("\n", "\r\n").encode("utf-8") + b"\r\n"
    assert parse_statement(data) == parse_statement(SAMPLE)


def test_rejects_cp1251():
    with pytest.raises(StatementError, match="UTF-8"):
        parse_statement(SAMPLE_TEXT.encode("cp1251"))


def test_rejects_missing_column():
    text = SAMPLE_TEXT.replace("Статус", "Состояние", 1)
    with pytest.raises(StatementError, match="«Статус»"):
        parse_statement(text.encode("utf-8"))


def test_rejects_empty_file():
    with pytest.raises(StatementError, match="Файл пуст"):
        parse_statement(b"")


@pytest.mark.parametrize(
    "data",
    [one_row(when="32.13.2026 25:00:00"), one_row(amount="-abc")],
)
def test_rejects_bad_row_with_line_number(data):
    with pytest.raises(StatementError, match="Строка 2"):
        parse_statement(data)

"""Разбор CSV-выписки банка в строки для экрана проверки."""

import csv
import io
from dataclasses import dataclass
from datetime import datetime

from app.money import parse_amount


class StatementError(ValueError):
    """Файл не похож на выписку или в нём битая строка."""


@dataclass(frozen=True)
class StatementRow:
    ref: str
    spent_on: str
    amount_kop: int
    note: str
    bank_category: str
    category: str
    selected: bool
    skip_reason: str | None


CATEGORY_MAP = {
    "Супермаркеты": "Продукты",
    "Рестораны": "Кафе",
    "Фастфуд": "Кафе",
    "Транспорт": "Транспорт",
    "Такси": "Транспорт",
    "Коммунальные услуги": "Дом",
    "Связь": "Дом",
    "Аптеки": "Здоровье",
    "Кино": "Развлечения",
    "Цифровые товары": "Развлечения",
}
FALLBACK_CATEGORY = "Другое"
TRANSFERS = "Переводы"

COLUMNS = [
    "Дата операции",
    "Номер карты",
    "Статус",
    "Сумма операции",
    "Валюта операции",
    "Категория",
    "Описание",
]


def parse_statement(data: bytes) -> list[StatementRow]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise StatementError("Файл должен быть в UTF-8") from None
    if not text.strip():
        raise StatementError("Файл пуст")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for column in COLUMNS:
        if column not in (reader.fieldnames or []):
            raise StatementError(f"Не похоже на выписку: нет колонки «{column}»")

    rows = []
    for record in reader:
        if not any((value or "").strip() for value in record.values()):
            continue
        try:
            rows.append(_parse_record(record))
        except ValueError as err:
            raise StatementError(f"Строка {reader.line_num}: {err}") from None
    return rows


def _parse_record(record: dict[str, str]) -> StatementRow:
    when = datetime.strptime(record["Дата операции"].strip(), "%d.%m.%Y %H:%M:%S")
    amount_text = record["Сумма операции"].strip()
    is_expense = amount_text.startswith("-")
    amount_kop = parse_amount(amount_text.removeprefix("-"))
    note = record["Описание"].strip()
    bank_category = record["Категория"].strip()

    if record["Статус"].strip() != "OK":
        skip_reason = "не прошла"
    elif not is_expense:
        skip_reason = "зачисление"
    elif record["Валюта операции"].strip() != "RUB":
        skip_reason = "не рубли"
    else:
        skip_reason = None

    signed = -amount_kop if is_expense else amount_kop
    return StatementRow(
        ref=f"{when.isoformat()}|{record['Номер карты'].strip()}|{signed}|{note}",
        spent_on=when.date().isoformat(),
        amount_kop=amount_kop,
        note=note,
        bank_category=bank_category,
        category=CATEGORY_MAP.get(bank_category, FALLBACK_CATEGORY),
        selected=skip_reason is None and bank_category != TRANSFERS,
        skip_reason=skip_reason,
    )

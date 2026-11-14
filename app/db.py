import os
import sqlite3

CATEGORIES = [
    "Продукты",
    "Кафе",
    "Транспорт",
    "Дом",
    "Здоровье",
    "Развлечения",
    "Другое",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spent_on TEXT NOT NULL,
    amount_kop INTEGER NOT NULL,
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    bank_ref TEXT
)
"""


def db_path() -> str:
    return os.environ.get("EXPENSES_DB", "expenses.db")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(SCHEMA)
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(expenses)")}
        if "bank_ref" not in columns:
            conn.execute("ALTER TABLE expenses ADD COLUMN bank_ref TEXT")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS expenses_bank_ref ON expenses(bank_ref)"
        )


def add_expense(spent_on: str, amount_kop: int, category: str, note: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (spent_on, amount_kop, category, note) VALUES (?, ?, ?, ?)",
            (spent_on, amount_kop, category, note),
        )
        return cur.lastrowid


def known_refs(refs: list[str]) -> set[str]:
    """Какие из ключей банковских операций уже есть в базе."""
    if not refs:
        return set()
    marks = ", ".join("?" * len(refs))
    with connect() as conn:
        rows = conn.execute(
            f"SELECT bank_ref FROM expenses WHERE bank_ref IN ({marks})", refs
        ).fetchall()
        return {row["bank_ref"] for row in rows}


def add_imported(rows: list[tuple[str, int, str, str, str]]) -> int:
    """Расходы из выписки: (дата, копейки, категория, комментарий, ключ).
    Уже загруженные ключи пропускаются; возвращает число добавленных."""
    added = 0
    with connect() as conn:
        for row in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO expenses "
                "(spent_on, amount_kop, category, note, bank_ref) VALUES (?, ?, ?, ?, ?)",
                row,
            )
            added += cur.rowcount
    return added


def list_month(month: str) -> list[sqlite3.Row]:
    """Расходы за месяц вида 2026-11, свежие сверху."""
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM expenses WHERE substr(spent_on, 1, 7) = ? "
            "ORDER BY spent_on DESC, id DESC",
            (month,),
        ).fetchall()


def month_total(month: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount_kop), 0) FROM expenses WHERE substr(spent_on, 1, 7) = ?",
            (month,),
        ).fetchone()
        return row[0]


def by_category(month: str) -> list[tuple[str, int]]:
    """Суммы по категориям за месяц, крупные сверху."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT category, SUM(amount_kop) AS total FROM expenses "
            "WHERE substr(spent_on, 1, 7) = ? GROUP BY category ORDER BY total DESC",
            (month,),
        ).fetchall()
        return [(r["category"], r["total"]) for r in rows]


def delete_expense(expense_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

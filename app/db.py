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
    note TEXT NOT NULL DEFAULT ''
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


def add_expense(spent_on: str, amount_kop: int, category: str, note: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (spent_on, amount_kop, category, note) VALUES (?, ?, ?, ?)",
            (spent_on, amount_kop, category, note),
        )
        return cur.lastrowid


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

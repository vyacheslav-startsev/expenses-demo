import sqlite3

import pytest

from app import db

OLD_SCHEMA = """
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spent_on TEXT NOT NULL,
    amount_kop INTEGER NOT NULL,
    category TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
)
"""

COFFEE = ("2026-11-09", 28000, "Кафе", "Кофейня Зерно")


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("EXPENSES_DB", str(path))
    return path


def test_add_imported_skips_known_ref(db_file):
    db.init_db()
    rows = [(*COFFEE, "r1"), (*COFFEE, "r2")]
    assert db.add_imported(rows) == 2
    assert db.add_imported(rows) == 0
    assert db.month_total("2026-11") == 56000


def test_known_refs(db_file):
    db.init_db()
    db.add_imported([(*COFFEE, "r1")])
    assert db.known_refs(["r1", "r3"]) == {"r1"}
    assert db.known_refs([]) == set()


def test_manual_expenses_unaffected(db_file):
    db.init_db()
    db.add_expense("2026-11-01", 100, "Кафе")
    db.add_expense("2026-11-01", 100, "Кафе")
    assert db.month_total("2026-11") == 200


def test_migrates_old_db(db_file):
    with sqlite3.connect(db_file) as conn:
        conn.execute(OLD_SCHEMA)
        conn.execute(
            "INSERT INTO expenses (spent_on, amount_kop, category, note) "
            "VALUES ('2026-10-01', 500, 'Дом', 'старая')"
        )
    db.init_db()
    db.init_db()
    with sqlite3.connect(db_file) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(expenses)")]
    assert "bank_ref" in columns
    assert db.month_total("2026-10") == 500
    assert db.add_imported([(*COFFEE, "r1"), (*COFFEE, "r1")]) == 1

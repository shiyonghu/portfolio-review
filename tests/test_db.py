from pathlib import Path

from portfolio.db.connection import get_connection, init_db

EXPECTED_TABLES = frozenset(
    {
        "accounts",
        "classifications",
        "holdings_snapshot",
        "items",
        "snapshot_summary",
        "user_managed_holdings",
    }
)


def test_init_db_creates_holdings_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in tables}
    assert "holdings_snapshot" in names
    assert "snapshot_summary" in names
    assert "user_managed_holdings" in names


def test_init_db_creates_all_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in tables}
    assert names.issuperset(EXPECTED_TABLES)


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    init_db(conn)
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r[0] for r in tables}
    assert names.issuperset(EXPECTED_TABLES)


def test_foreign_keys_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row is not None
    assert row[0] == 1

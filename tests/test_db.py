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


def test_init_db_accounts_has_type_column(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    columns = conn.execute("PRAGMA table_info(accounts)").fetchall()
    conn.close()
    assert "type" in {row[1] for row in columns}


def test_foreign_keys_enabled(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    init_db(conn)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row is not None
    assert row[0] == 1


def test_accounts_allows_fidelity_with_null_tax_treatment(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, subtype, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("fid-1", None, "fidelity", "Fidelity Account", "investment", None, "household", 0, None),
    )
    row = conn.execute("SELECT source, tax_treatment FROM accounts WHERE account_id = ?", ("fid-1",)).fetchone()
    conn.close()
    assert dict(row) == {"source": "fidelity", "tax_treatment": None}


def test_holdings_snapshot_allows_fidelity_source(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("fid-1", None, "fidelity", "Fidelity Account", "investment", "household", 1, "taxable"),
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (snapshot_date, account_id, source, asset_name, display_name, value)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-16", "fid-1", "fidelity", "SPY", "SPDR S&P 500 ETF", 100.0),
    )
    row = conn.execute("SELECT source FROM holdings_snapshot WHERE account_id = ?", ("fid-1",)).fetchone()
    conn.close()
    assert row["source"] == "fidelity"

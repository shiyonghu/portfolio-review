import pytest

from portfolio.agent.tools import run_sql
from portfolio.db.connection import get_connection, init_db


def test_run_sql_rejects_insert(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    with pytest.raises(ValueError):
        run_sql(conn, "INSERT INTO items (item_id) VALUES ('x')")


def test_run_sql_rejects_delete(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    with pytest.raises(ValueError):
        run_sql(conn, "DELETE FROM items")


def test_run_sql_rejects_semicolon(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    with pytest.raises(ValueError):
        run_sql(conn, "SELECT item_id FROM items;")


def test_run_sql_caps_rows_at_500(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.executemany(
        """
        INSERT INTO items (item_id, institution_name, status, last_synced_at)
        VALUES (?, ?, ?, ?)
        """,
        [(f"item-{i}", "Inst", "ok", None) for i in range(520)],
    )
    conn.commit()

    rows = run_sql(conn, "SELECT item_id FROM items ORDER BY item_id")

    assert len(rows) == 500


def test_run_sql_unknown_table_returns_error_payload(tmp_path) -> None:
    """LLM-generated SQL may reference non-existent tables; agent should recover, not crash."""
    from portfolio.agent.tools import run_sql_for_agent

    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    out = run_sql_for_agent(conn, "SELECT 1 FROM portfolio LIMIT 1")
    assert out["rows"] == []
    assert "no such table" in out["error"].lower()
    assert "hint" in out

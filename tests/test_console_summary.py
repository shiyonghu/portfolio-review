from portfolio.db.connection import get_connection, init_db
from portfolio.snapshot.console import print_snapshot_summary


def test_print_snapshot_summary_includes_totals_drift_and_warnings(tmp_path, capsys) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    conn.executemany(
        """
        INSERT INTO items (item_id, institution_name, status, last_synced_at)
        VALUES (?, ?, ?, ?)
        """,
        [
            ("item-1", "Inst 1", "ok", None),
            ("item-2", "Inst 2", "login_required", None),
        ],
    )
    conn.executemany(
        """
        INSERT INTO accounts (account_id, item_id, source, name, subtype, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("a1", "item-1", "plaid", "Taxable", "brokerage", "household", 1, "taxable"),
            ("a2", "item-2", "plaid", "IRA", "ira", "household", 1, "tax-advantaged"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO snapshot_summary (snapshot_date, bucket, tax_treatment, owner_tag, total_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("2026-05-12", "Bond", "taxable", "household", 300.0),
            ("2026-05-12", "Equity", "taxable", "household", 700.0),
            ("2026-05-13", "Bond", "taxable", "household", 400.0),
            ("2026-05-13", "Equity", "taxable", "household", 600.0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name, value, bucket
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-05-13", "a1", "plaid", "BND", "BND", 400.0, "Bond"),
            ("2026-05-13", "a2", "plaid", "VTI", "VTI", 600.0, "Equity"),
            ("2026-05-13", "a2", "plaid", "UNKNOWN", "UNKNOWN", 50.0, None),
        ],
    )
    conn.commit()

    print_snapshot_summary(conn, "2026-05-13")
    output = capsys.readouterr().out

    assert "Total net worth: $1,000.00" in output
    assert "Bond: 40.00%" in output
    assert "Equity: 60.00%" in output
    assert "Bond: +10.00 pp" in output
    assert "Equity: -10.00 pp" in output
    assert "item-2" in output
    assert "login_required" in output
    assert "UNKNOWN" in output

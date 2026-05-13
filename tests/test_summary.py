from portfolio.db.connection import get_connection, init_db
from portfolio.snapshot.summary import rebuild_snapshot_summary


def test_rebuild_snapshot_summary_groups_by_bucket_tax_and_owner(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, subtype, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("a-taxable", None, "user_managed", "Taxable A", "other", "household", 1, "taxable"),
    )
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, subtype, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "a-adv",
            None,
            "user_managed",
            "Advantaged A",
            "other",
            "household",
            1,
            "tax-advantaged",
        ),
    )
    conn.executemany(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name, value, bucket
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("2026-05-13", "a-taxable", "user_managed", "VTI", "VTI", 1000.0, "Equity"),
            ("2026-05-13", "a-taxable", "user_managed", "BND", "BND", 500.0, "Bond"),
            ("2026-05-13", "a-adv", "user_managed", "VTI", "VTI", 700.0, "Equity"),
        ],
    )
    conn.commit()

    rebuild_snapshot_summary(conn, "2026-05-13")
    rows = conn.execute(
        """
        SELECT bucket, tax_treatment, owner_tag, total_value
        FROM snapshot_summary
        WHERE snapshot_date = ?
        ORDER BY bucket, tax_treatment
        """,
        ("2026-05-13",),
    ).fetchall()

    assert [(r["bucket"], r["tax_treatment"], r["total_value"]) for r in rows] == [
        ("Bond", "taxable", 500.0),
        ("Equity", "tax-advantaged", 700.0),
        ("Equity", "taxable", 1000.0),
    ]

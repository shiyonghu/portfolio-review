from pathlib import Path

from portfolio.db.connection import get_connection, init_db
from portfolio.snapshot.export_csv import export_snapshot_csv


def test_export_snapshot_csv_has_detail_and_summary_without_quantity(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, subtype, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("acc-1", None, "user_managed", "Manual Account", "other", "household", 1, "taxable"),
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name, value, bucket, quantity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-13", "acc-1", "user_managed", "Primary Home", "Primary Home", 900000, "RealEstate", 1.0),
    )
    conn.execute(
        """
        INSERT INTO snapshot_summary (snapshot_date, bucket, tax_treatment, owner_tag, total_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("2026-05-13", "RealEstate", "taxable", "household", 900000),
    )
    conn.commit()

    out_path = tmp_path / "snapshot.csv"
    export_snapshot_csv(conn, "2026-05-13", out_path)
    content = out_path.read_text()

    assert "DETAIL" in content
    assert "SUMMARY" in content
    assert "snapshot_date,account_name,asset_name,bucket,value,tax_treatment,owner_tag,source" in content
    assert "quantity" not in content.lower()
    assert "Primary Home" in content
    assert "RealEstate,taxable,household,900000.0" in content

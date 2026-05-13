from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


def export_snapshot_csv(conn: sqlite3.Connection, snapshot_date: str, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    detail_rows = conn.execute(
        """
        SELECT
            hs.snapshot_date,
            a.name AS account_name,
            hs.asset_name,
            hs.bucket,
            hs.value,
            a.tax_treatment,
            a.owner_tag,
            hs.source
        FROM holdings_snapshot hs
        JOIN accounts a ON a.account_id = hs.account_id
        WHERE hs.snapshot_date = ? AND a.included = 1
        ORDER BY a.name, hs.asset_name
        """,
        (snapshot_date,),
    ).fetchall()

    summary_rows = conn.execute(
        """
        SELECT bucket, tax_treatment, owner_tag, total_value
        FROM snapshot_summary
        WHERE snapshot_date = ?
        ORDER BY bucket, tax_treatment, owner_tag
        """,
        (snapshot_date,),
    ).fetchall()

    with out_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["DETAIL"])
        writer.writerow(
            [
                "snapshot_date",
                "account_name",
                "asset_name",
                "bucket",
                "value",
                "tax_treatment",
                "owner_tag",
                "source",
            ]
        )
        for row in detail_rows:
            writer.writerow(
                [
                    row["snapshot_date"],
                    row["account_name"],
                    row["asset_name"],
                    row["bucket"],
                    row["value"],
                    row["tax_treatment"],
                    row["owner_tag"],
                    row["source"],
                ]
            )

        writer.writerow([])
        writer.writerow(["SUMMARY"])
        writer.writerow(["bucket", "tax_treatment", "owner_tag", "total_value"])
        for row in summary_rows:
            writer.writerow(
                [
                    row["bucket"],
                    row["tax_treatment"],
                    row["owner_tag"],
                    row["total_value"],
                ]
            )

    return out_path

from __future__ import annotations

import sqlite3


def rebuild_snapshot_summary(conn: sqlite3.Connection, snapshot_date: str) -> None:
    conn.execute(
        "DELETE FROM snapshot_summary WHERE snapshot_date = ?",
        (snapshot_date,),
    )
    conn.execute(
        """
        INSERT INTO snapshot_summary (
            snapshot_date, bucket, tax_treatment, owner_tag, total_value
        )
        SELECT
            hs.snapshot_date,
            hs.bucket,
            a.tax_treatment,
            a.owner_tag,
            SUM(hs.value)
        FROM holdings_snapshot hs
        JOIN accounts a ON a.account_id = hs.account_id
        WHERE hs.snapshot_date = ? AND a.included = 1 AND hs.bucket IS NOT NULL
        GROUP BY hs.snapshot_date, hs.bucket, a.tax_treatment, a.owner_tag
        """,
        (snapshot_date,),
    )
    conn.commit()

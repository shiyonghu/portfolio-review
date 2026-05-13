from __future__ import annotations

import sqlite3


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def print_snapshot_summary(conn: sqlite3.Connection, snapshot_date: str) -> None:
    total_row = conn.execute(
        """
        SELECT COALESCE(SUM(total_value), 0) AS net_worth
        FROM snapshot_summary
        WHERE snapshot_date = ?
        """,
        (snapshot_date,),
    ).fetchone()
    net_worth = float(total_row["net_worth"]) if total_row is not None else 0.0

    print(f"Total net worth: {_format_money(net_worth)}")

    bucket_rows = conn.execute(
        """
        SELECT bucket, SUM(total_value) AS bucket_total
        FROM snapshot_summary
        WHERE snapshot_date = ?
        GROUP BY bucket
        ORDER BY bucket_total DESC, bucket
        """,
        (snapshot_date,),
    ).fetchall()
    print("Bucket allocation:")
    if not bucket_rows:
        print("- none")
    else:
        for row in bucket_rows:
            bucket = str(row["bucket"])
            bucket_total = float(row["bucket_total"])
            pct = (bucket_total / net_worth * 100.0) if net_worth > 0 else 0.0
            print(f"- {bucket}: {pct:.2f}% ({_format_money(bucket_total)})")

    prev_row = conn.execute(
        """
        SELECT MAX(snapshot_date) AS prev_date
        FROM snapshot_summary
        WHERE snapshot_date < ?
        """,
        (snapshot_date,),
    ).fetchone()
    prev_date = str(prev_row["prev_date"]) if prev_row and prev_row["prev_date"] else None

    print("Drift vs previous snapshot:")
    if prev_date is None:
        print("- none")
    else:
        current = {
            str(row["bucket"]): float(row["bucket_total"])
            for row in bucket_rows
        }
        prev_rows = conn.execute(
            """
            SELECT bucket, SUM(total_value) AS bucket_total
            FROM snapshot_summary
            WHERE snapshot_date = ?
            GROUP BY bucket
            """,
            (prev_date,),
        ).fetchall()
        previous = {str(row["bucket"]): float(row["bucket_total"]) for row in prev_rows}
        prev_total = sum(previous.values())
        for bucket in sorted(set(current) | set(previous)):
            curr_pct = (current.get(bucket, 0.0) / net_worth * 100.0) if net_worth > 0 else 0.0
            prev_pct = (previous.get(bucket, 0.0) / prev_total * 100.0) if prev_total > 0 else 0.0
            drift = curr_pct - prev_pct
            print(f"- {bucket}: {drift:+.2f} pp")

    item_rows = conn.execute(
        """
        SELECT item_id, institution_name, status
        FROM items
        WHERE status IS NOT NULL AND status != 'ok'
        ORDER BY item_id
        """
    ).fetchall()
    print("Items needing attention:")
    if not item_rows:
        print("- none")
    else:
        for row in item_rows:
            item_id = str(row["item_id"])
            status = str(row["status"])
            institution = str(row["institution_name"] or "unknown")
            print(f"- {item_id} ({institution}): {status}")

    unclassified_rows = conn.execute(
        """
        SELECT account_id, asset_name, value
        FROM holdings_snapshot
        WHERE snapshot_date = ? AND bucket IS NULL
        ORDER BY value DESC, asset_name
        """,
        (snapshot_date,),
    ).fetchall()
    print("Unclassified holdings (NULL bucket):")
    if not unclassified_rows:
        print("- none")
    else:
        for row in unclassified_rows:
            print(
                f"- {row['asset_name']} account={row['account_id']} "
                f"value={_format_money(float(row['value']))}"
            )

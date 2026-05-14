from __future__ import annotations

import re
import sqlite3
from typing import Any

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|reindex|begin|commit|rollback)\b",
    re.IGNORECASE,
)

_READ_ONLY_PREFIXES = ("select", "with")

# Shown to the model with run_sql so it uses real table/column names (there is no "portfolio" table).
SQL_SCHEMA_HINT = (
    "SQLite schema: items(item_id, institution_name, …); "
    "accounts(account_id, item_id, name, …); "
    "holdings_snapshot(snapshot_date, account_id, bucket, value, asset_name, …); "
    "snapshot_summary(snapshot_date, bucket, tax_treatment, owner_tag, total_value); "
    "classifications(asset_name, bucket, …); user_managed_holdings(…). "
    "For latest snapshot totals by bucket, query snapshot_summary or aggregate holdings_snapshot "
    "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM holdings_snapshot)."
)


def _guard_select_only(query: str) -> str:
    normalized = query.strip()
    if not normalized:
        raise ValueError("Query is empty")
    if ";" in normalized:
        raise ValueError("Semicolons are not allowed")
    if not normalized.lower().startswith(_READ_ONLY_PREFIXES):
        raise ValueError("Only SELECT queries are allowed")
    if _FORBIDDEN_SQL.search(normalized):
        raise ValueError("Only read-only SQL is allowed")
    return normalized


def run_sql(conn: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    guarded_query = _guard_select_only(query)
    rows = conn.execute(
        f"SELECT * FROM ({guarded_query}) AS safe_query LIMIT 500"
    ).fetchall()
    return [dict(row) for row in rows]


def run_sql_for_agent(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Like run_sql but returns a dict the LLM can interpret; SQLite errors do not raise."""
    try:
        return {"rows": run_sql(conn, query)}
    except sqlite3.OperationalError as exc:
        return {
            "rows": [],
            "error": str(exc),
            "hint": SQL_SCHEMA_HINT,
        }

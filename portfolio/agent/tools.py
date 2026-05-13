from __future__ import annotations

import re
import sqlite3
from typing import Any

_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|vacuum|reindex|begin|commit|rollback)\b",
    re.IGNORECASE,
)

_READ_ONLY_PREFIXES = ("select", "with")


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

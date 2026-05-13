from __future__ import annotations

import sqlite3
from typing import Any
from uuid import uuid4


def _new_account_id(asset_name: str) -> str:
    slug = "-".join(asset_name.strip().lower().split())
    return f"managed-{slug}-{uuid4().hex[:8]}"


def _require_asset_account(conn: sqlite3.Connection, asset_name: str) -> str:
    row = conn.execute(
        """
        SELECT account_id
        FROM user_managed_holdings
        WHERE asset_name = ? AND is_active = 1
        ORDER BY effective_date DESC, id DESC
        LIMIT 1
        """,
        (asset_name,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Unknown managed asset: {asset_name}")
    return str(row["account_id"])


def add_managed_asset(
    conn: sqlite3.Connection,
    *,
    asset_name: str,
    asset_kind: str,
    value: float,
    effective_date: str,
    source: str = "manual",
    notes: str | None = None,
    owner_tag: str = "household",
    tax_treatment: str = "taxable",
) -> str:
    existing = conn.execute(
        """
        SELECT 1 FROM user_managed_holdings
        WHERE asset_name = ? AND is_active = 1
        LIMIT 1
        """,
        (asset_name,),
    ).fetchone()
    if existing is not None:
        raise ValueError(f"Managed asset already exists: {asset_name}")

    account_id = _new_account_id(asset_name)
    conn.execute(
        """
        INSERT INTO accounts (
            account_id, item_id, source, name, subtype, owner_tag, included, tax_treatment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            None,
            "user_managed",
            f"Managed: {asset_name}",
            asset_kind,
            owner_tag,
            1,
            tax_treatment,
        ),
    )
    conn.execute(
        """
        INSERT INTO user_managed_holdings (
            asset_name, asset_kind, account_id, value, effective_date, source, notes, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (asset_name, asset_kind, account_id, float(value), effective_date, source, notes),
    )
    conn.commit()
    return account_id


def append_valuation(
    conn: sqlite3.Connection,
    *,
    asset_name: str,
    value: float,
    effective_date: str,
    source: str,
    notes: str | None = None,
) -> str:
    account_id = _require_asset_account(conn, asset_name)
    cursor = conn.execute(
        """
        INSERT INTO user_managed_holdings (
            asset_name, asset_kind, account_id, value, effective_date, source, notes, is_active
        )
        SELECT asset_name, asset_kind, account_id, ?, ?, ?, ?, 1
        FROM user_managed_holdings
        WHERE asset_name = ? AND is_active = 1
        ORDER BY effective_date DESC, id DESC
        LIMIT 1
        """,
        (float(value), effective_date, source, notes, asset_name),
    )
    conn.commit()
    return str(cursor.lastrowid)


def resolve_valuation(
    conn: sqlite3.Connection,
    asset_name: str,
    as_of_date: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM user_managed_holdings
        WHERE asset_name = ? AND is_active = 1 AND effective_date <= ?
        ORDER BY effective_date DESC, id DESC
        LIMIT 1
        """,
        (asset_name, as_of_date),
    ).fetchone()
    return dict(row) if row is not None else None


def materialize_managed_rows(
    conn: sqlite3.Connection,
    snapshot_date: str,
) -> list[dict[str, Any]]:
    assets = conn.execute(
        """
        SELECT DISTINCT asset_name
        FROM user_managed_holdings
        WHERE is_active = 1
        ORDER BY asset_name
        """
    ).fetchall()
    rows: list[dict[str, Any]] = []
    for asset_row in assets:
        asset_name = str(asset_row["asset_name"])
        valuation = resolve_valuation(conn, asset_name, snapshot_date)
        if valuation is None:
            continue
        rows.append(
            {
                "snapshot_date": snapshot_date,
                "account_id": valuation["account_id"],
                "source": "user_managed",
                "asset_name": valuation["asset_name"],
                "asset_kind": valuation["asset_kind"],
                "display_name": valuation["asset_name"],
                "plaid_security_id": None,
                "plaid_type": None,
                "plaid_subtype": None,
                "is_cash_equivalent": None,
                "quantity": None,
                "unit_price": None,
                "price_as_of": None,
                "value": valuation["value"],
            }
        )
    return rows


def list_latest(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT asset_name, asset_kind, account_id, value, effective_date, source, notes
        FROM (
            SELECT
                umh.*,
                ROW_NUMBER() OVER (
                    PARTITION BY asset_name
                    ORDER BY effective_date DESC, id DESC
                ) AS rn
            FROM user_managed_holdings umh
            WHERE is_active = 1
        )
        WHERE rn = 1
        ORDER BY asset_name
        """
    ).fetchall()
    return [dict(row) for row in rows]

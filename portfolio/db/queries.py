from __future__ import annotations

import sqlite3
from typing import Any


def list_accounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT account_id, name, included, owner_tag, tax_treatment, subtype, source
        FROM accounts
        ORDER BY name
        """
    ).fetchall()


def get_account(conn: sqlite3.Connection, account_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM accounts WHERE account_id = ?",
        (account_id,),
    ).fetchone()


def update_account(
    conn: sqlite3.Connection,
    account_id: str,
    *,
    included: bool | None = None,
    owner_tag: str | None = None,
    tax_treatment: str | None = None,
) -> None:
    account = get_account(conn, account_id)
    if account is None:
        raise ValueError(f"Unknown account_id: {account_id}")

    fields: list[str] = []
    values: list[Any] = []
    if included is not None:
        fields.append("included = ?")
        values.append(1 if included else 0)
    if owner_tag is not None:
        fields.append("owner_tag = ?")
        values.append(owner_tag)
    if tax_treatment is not None:
        if tax_treatment not in {"taxable", "tax-advantaged"}:
            raise ValueError("tax_treatment must be 'taxable' or 'tax-advantaged'")
        fields.append("tax_treatment = ?")
        fields.append("tax_treatment_override = ?")
        values.extend([tax_treatment, tax_treatment])

    if not fields:
        return

    values.append(account_id)
    conn.execute(
        f"UPDATE accounts SET {', '.join(fields)} WHERE account_id = ?",
        values,
    )
    conn.commit()

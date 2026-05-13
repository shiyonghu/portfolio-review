"""Persist Plaid accounts under an item with per-account inclusion."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import sqlite3

from portfolio.accounts.tax import derive_tax_treatment


def _plaid_str(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        raw = value.value
        return str(raw) if raw is not None else None
    return str(value)


def upsert_plaid_accounts(
    conn: sqlite3.Connection,
    item_id: str,
    accounts: Sequence[Any],
    included_account_ids: Iterable[str],
) -> int:
    """Upsert Plaid accounts for an item; mark selected ids as included."""
    included = {str(account_id) for account_id in included_account_ids}
    for account in accounts:
        account_id = str(account.account_id)
        subtype = _plaid_str(account.subtype)
        account_type = _plaid_str(getattr(account, "type", None))
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, item_id, source, name, type, subtype, owner_tag, included, tax_treatment
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                item_id = excluded.item_id,
                source = excluded.source,
                name = excluded.name,
                type = excluded.type,
                subtype = excluded.subtype,
                included = excluded.included
            """,
            (
                account_id,
                item_id,
                "plaid",
                account.name,
                account_type,
                subtype,
                "household",
                1 if account_id in included else 0,
                derive_tax_treatment(subtype),
            ),
        )
    conn.commit()
    return len(accounts)


def serialize_plaid_accounts(accounts: Sequence[Any]) -> list[dict[str, str | None]]:
    return [
        {
            "account_id": str(account.account_id),
            "name": account.name,
            "subtype": _plaid_str(account.subtype),
            "type": _plaid_str(getattr(account, "type", None)),
        }
        for account in accounts
    ]

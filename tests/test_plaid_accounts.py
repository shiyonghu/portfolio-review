from __future__ import annotations

from unittest.mock import MagicMock

from plaid.model.account_subtype import AccountSubtype

from portfolio.db.connection import get_connection, init_db
from portfolio.plaid.accounts import upsert_plaid_accounts


def _account(account_id: str, name: str, subtype: str, account_type: str = "investment") -> MagicMock:
    account = MagicMock()
    account.account_id = account_id
    account.name = name
    account.subtype = AccountSubtype(subtype)
    account.type = account_type
    return account


def test_upsert_plaid_accounts_marks_selection(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        "INSERT INTO items (item_id, institution_name, status) VALUES (?, ?, ?)",
        ("item-1", "Bank", "ok"),
    )
    conn.commit()

    accounts = [
        _account("acct-1", "Brokerage", "brokerage", "investment"),
        _account("acct-2", "401k", "401k", "investment"),
    ]
    upsert_plaid_accounts(conn, "item-1", accounts, included_account_ids=["acct-2"])

    rows = conn.execute(
        "SELECT account_id, type, included, tax_treatment FROM accounts ORDER BY account_id"
    ).fetchall()
    conn.close()

    assert [dict(row) for row in rows] == [
        {"account_id": "acct-1", "type": "investment", "included": 0, "tax_treatment": "taxable"},
        {"account_id": "acct-2", "type": "investment", "included": 1, "tax_treatment": "tax-advantaged"},
    ]

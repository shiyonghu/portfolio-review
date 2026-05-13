from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def _to_bool_int(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def normalize_plaid_item(
    accounts: Sequence[Mapping[str, Any]],
    holdings_response: Mapping[str, Any],
    balances_response: Mapping[str, Any],
    snapshot_date: str,
) -> list[dict[str, Any]]:
    """Normalize Plaid holdings + balances into holdings_snapshot-style rows."""
    account_by_id = {str(account["account_id"]): account for account in accounts}
    securities = holdings_response.get("securities", [])
    security_by_id = {
        str(security["security_id"]): security
        for security in securities
        if security.get("security_id") is not None
    }

    rows: list[dict[str, Any]] = []

    for holding in holdings_response.get("holdings", []):
        security_id = holding.get("security_id")
        if security_id is None:
            continue

        account_id = str(holding.get("account_id") or "")
        if account_id not in account_by_id:
            continue
        security = security_by_id.get(str(security_id), {})
        ticker = str(security.get("ticker_symbol") or "").strip()
        asset_name = ticker or str(security_id)

        rows.append(
            {
                "snapshot_date": snapshot_date,
                "account_id": account_id,
                "source": "plaid",
                "asset_name": asset_name,
                "display_name": security.get("name") or asset_name,
                "plaid_security_id": str(security_id),
                "plaid_type": security.get("type"),
                "plaid_subtype": security.get("subtype"),
                "is_cash_equivalent": _to_bool_int(security.get("is_cash_equivalent")),
                "quantity": holding.get("quantity"),
                "unit_price": holding.get("institution_price"),
                "price_as_of": holding.get("institution_price_as_of"),
                "value": holding.get("institution_value") or 0.0,
            }
        )

    for balance_account in balances_response.get("accounts", []):
        account_id = str(balance_account.get("account_id") or "")
        if account_id not in account_by_id:
            continue

        account = account_by_id[account_id]
        account_type = str(account.get("type") or balance_account.get("type") or "").lower()
        if account_type != "depository":
            continue

        current = (balance_account.get("balances") or {}).get("current")
        if current is None:
            continue

        rows.append(
            {
                "snapshot_date": snapshot_date,
                "account_id": account_id,
                "source": "plaid",
                "asset_name": "cash",
                "display_name": "cash",
                "plaid_security_id": None,
                "plaid_type": "cash",
                "plaid_subtype": account.get("subtype"),
                "is_cash_equivalent": 1,
                "quantity": None,
                "unit_price": 1.0,
                "price_as_of": None,
                "value": current,
            }
        )

    return rows

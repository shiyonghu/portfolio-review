from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path
from typing import Any


REQUIRED_HEADERS = {
    "Account Number",
    "Account Name",
    "Symbol",
    "Description",
    "Quantity",
    "Last Price",
    "Current Value",
}


class FidelityCsvError(ValueError):
    """Raised when a Fidelity positions CSV cannot be parsed."""


def parse_optional_float(value: Any) -> float | None:
    """Parse Fidelity numeric strings, returning None for blank placeholders."""
    if value is None:
        return None

    text = str(value).strip()
    if text in {"", "--"}:
        return None

    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1]

    cleaned = text.replace("$", "").replace(",", "").replace("%", "").strip()
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]

    try:
        number = float(cleaned)
    except ValueError as exc:
        raise FidelityCsvError(f"could not parse numeric value: {value!r}") from exc
    return -number if negative_parentheses else number


def discover_accounts(path: str | Path) -> list[dict[str, str]]:
    """Return unique Fidelity accounts present in the positions CSV."""
    accounts: set[tuple[str, str]] = set()
    for row in _read_position_rows(path):
        account_id = row.get("Account Number", "")
        account_name = row.get("Account Name", "")
        if account_id and account_name:
            accounts.add((account_id, account_name))

    return [
        {"account_id": account_id, "name": name}
        for account_id, name in sorted(accounts)
    ]


def validate_snapshot_accounts(
    path: Path,
    *,
    configured_accounts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    csv_account_ids = {account["account_id"] for account in discover_accounts(path)}
    missing = sorted(
        account_id for account_id in csv_account_ids if account_id not in configured_accounts
    )
    if missing:
        raise FidelityCsvError(
            "Fidelity accounts not set up: "
            + ", ".join(missing)
            + ". Run `portfolio fidelity setup --csv <file>`."
        )
    included = {
        account_id: account
        for account_id, account in configured_accounts.items()
        if account_id in csv_account_ids and int(account.get("included") or 0) == 1
    }
    missing_tax = sorted(
        account_id
        for account_id, account in included.items()
        if account.get("tax_treatment") is None
    )
    if missing_tax:
        raise FidelityCsvError(
            "Included Fidelity accounts missing tax treatment: " + ", ".join(missing_tax)
        )
    return included


def normalize_holdings(
    path: str | Path,
    *,
    snapshot_date: str,
    included_accounts: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize Fidelity positions into holdings_snapshot-style rows."""
    included_account_ids = {str(account_id) for account_id in included_accounts}
    rows: list[dict[str, Any]] = []
    row_by_snapshot_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for csv_row in _read_position_rows(path):
        account_id = csv_row.get("Account Number", "")
        if account_id not in included_account_ids:
            continue

        symbol = csv_row.get("Symbol", "").strip()
        if not symbol:
            continue

        description = csv_row.get("Description", "").strip()
        quantity = _parse_row_float(csv_row, "Quantity")
        value = _parse_row_float(csv_row, "Current Value", required=True)
        row = {
            "snapshot_date": snapshot_date,
            "account_id": account_id,
            "source": "fidelity",
            "asset_name": symbol,
            "display_name": description or symbol,
            "plaid_security_id": None,
            "plaid_type": None,
            "plaid_subtype": None,
            "is_cash_equivalent": 1 if _is_cash_equivalent(symbol, description) else 0,
            "quantity": quantity,
            "unit_price": _parse_row_float(csv_row, "Last Price"),
            "price_as_of": snapshot_date,
            "value": value,
        }

        snapshot_key = (snapshot_date, account_id, symbol, "fidelity")
        existing_row = row_by_snapshot_key.get(snapshot_key)
        if existing_row is None:
            row_by_snapshot_key[snapshot_key] = row
            rows.append(row)
        else:
            _merge_duplicate_holding(existing_row, row)

    return rows


def _read_position_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        _validate_headers(reader.fieldnames)

        rows: list[dict[str, str]] = []
        for row_number, raw_row in enumerate(reader, start=2):
            row = _clean_row(raw_row)
            if _is_blank_row(row) or _is_trailer_row(row):
                break
            row["__row_number"] = str(row_number)
            rows.append(row)
        return rows


def _validate_headers(fieldnames: list[str] | None) -> None:
    headers = {header.strip() for header in fieldnames or [] if header is not None}
    missing = sorted(REQUIRED_HEADERS - headers)
    if missing:
        raise FidelityCsvError(f"missing required headers: {', '.join(missing)}")


def _clean_row(row: Mapping[Any, Any]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        cleaned[str(key).strip()] = "" if value is None else str(value).strip()
    return cleaned


def _is_blank_row(row: Mapping[str, str]) -> bool:
    return not any(value.strip() for value in row.values())


def _is_trailer_row(row: Mapping[str, str]) -> bool:
    nonempty_values = [value.strip().strip('"') for value in row.values() if value.strip()]
    if not nonempty_values:
        return False
    first_value = nonempty_values[0].lower()
    return first_value.startswith(
        (
            "brokerage services are provided",
            "date downloaded",
            "downloaded",
            "the data and information in this spreadsheet",
        )
    )


def _is_cash_equivalent(symbol: str, description: str) -> bool:
    normalized_description = description.upper()
    return (
        symbol.endswith("**")
        or "HELD IN MONEY MARKET" in normalized_description
        or "BANK DEPOSIT PORTFOLIO" in normalized_description
    )


def _parse_row_float(
    row: Mapping[str, str],
    field_name: str,
    *,
    required: bool = False,
) -> float | None:
    raw_value = row.get(field_name)
    try:
        value = parse_optional_float(raw_value)
    except FidelityCsvError as exc:
        raise FidelityCsvError(
            f"row {row.get('__row_number', '?')} account {row.get('Account Number', '')} "
            f"symbol {row.get('Symbol', '')}: invalid {field_name} {raw_value!r}"
        ) from exc

    if required and value is None:
        raise FidelityCsvError(
            f"row {row.get('__row_number', '?')} account {row.get('Account Number', '')} "
            f"symbol {row.get('Symbol', '')}: missing required {field_name}"
        )
    return value


def _merge_duplicate_holding(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["value"] = float(existing.get("value") or 0.0) + float(incoming.get("value") or 0.0)
    existing["quantity"] = _sum_optional_numbers(existing.get("quantity"), incoming.get("quantity"))
    if existing["quantity"]:
        existing["unit_price"] = existing["value"] / existing["quantity"]
    existing["is_cash_equivalent"] = 1 if existing["is_cash_equivalent"] or incoming["is_cash_equivalent"] else 0


def _sum_optional_numbers(left: Any, right: Any) -> float | None:
    values = [value for value in (left, right) if value is not None]
    if not values:
        return None
    return sum(float(value) for value in values)

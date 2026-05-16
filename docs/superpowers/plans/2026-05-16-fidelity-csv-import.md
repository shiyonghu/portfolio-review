# Fidelity CSV Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Fidelity positions CSV account setup and optional snapshot ingestion as a first-class local source.

**Architecture:** Add a small `portfolio/fidelity/` package for CSV parsing, account setup, and holding normalization. Extend the SQLite schema so `fidelity` is an allowed source and excluded accounts can have null tax treatment. Existing local `accounts` and `holdings_snapshot` tables will be manually recreated; no automated migration is required. Wire the CLI with `portfolio fidelity setup --csv <path>` and `portfolio snapshot --fidelity-csv <path>`.

**Tech Stack:** Python 3.12, Typer, SQLite, pytest, standard-library `csv`, existing snapshot/classification pipeline.

**Authoritative spec:** `docs/superpowers/specs/2026-05-16-fidelity-csv-import-design.md`

---

## File Structure

- Create `portfolio/fidelity/__init__.py`: package marker.
- Create `portfolio/fidelity/csv.py`: parse Fidelity CSV rows, discover accounts, normalize included holdings.
- Create `portfolio/fidelity/accounts.py`: upsert discovered Fidelity accounts and run prompt-driven setup.
- Modify `portfolio/db/schema.sql`: allow `fidelity` sources and nullable `accounts.tax_treatment`.
- Modify `portfolio/db/queries.py`: allow null tax treatment where account listing/updating needs it.
- Modify `portfolio/snapshot/runner.py`: accept optional Fidelity CSV path and insert normalized Fidelity rows.
- Modify `portfolio/cli.py`: add `fidelity setup` subcommand and `snapshot --fidelity-csv`.
- Create `tests/test_fidelity_csv.py`: parser, account discovery, normalization, and validation tests.
- Create `tests/test_fidelity_accounts.py`: interactive setup/account persistence tests.
- Modify `tests/test_db.py`: schema coverage for fresh/recreated tables.
- Modify `tests/test_export_csv.py` or add focused snapshot-runner tests if needed for source compatibility.

---

## Task 1: Schema Support For Fidelity Source

**Files:**

- Modify: `tests/test_db.py`
- Modify: `portfolio/db/schema.sql`

- [ ] **Step 1: Add schema tests for Fidelity source and nullable tax treatment**

Append these tests to `tests/test_db.py`:

```python
def test_accounts_allows_fidelity_with_null_tax_treatment(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, subtype, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("fid-1", None, "fidelity", "Fidelity Account", "investment", None, "household", 0, None),
    )
    row = conn.execute("SELECT source, tax_treatment FROM accounts WHERE account_id = ?", ("fid-1",)).fetchone()
    conn.close()
    assert dict(row) == {"source": "fidelity", "tax_treatment": None}


def test_holdings_snapshot_allows_fidelity_source(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("fid-1", None, "fidelity", "Fidelity Account", "investment", "household", 1, "taxable"),
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (snapshot_date, account_id, source, asset_name, display_name, value)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-16", "fid-1", "fidelity", "SPY", "SPDR S&P 500 ETF", 100.0),
    )
    row = conn.execute("SELECT source FROM holdings_snapshot WHERE account_id = ?", ("fid-1",)).fetchone()
    conn.close()
    assert row["source"] == "fidelity"
```

- [ ] **Step 2: Run the schema tests and verify they fail**

Run:

```bash
pytest tests/test_db.py::test_accounts_allows_fidelity_with_null_tax_treatment tests/test_db.py::test_holdings_snapshot_allows_fidelity_source -q
```

Expected: FAIL because the current schema rejects `source='fidelity'` and `tax_treatment=NULL`.

- [ ] **Step 3: Update the base schema**

In `portfolio/db/schema.sql`, change the account and holding source checks and make `tax_treatment` nullable:

```sql
source TEXT NOT NULL CHECK (source IN ('plaid', 'fidelity', 'user_managed')),
```

For `accounts.tax_treatment`, replace:

```sql
tax_treatment TEXT NOT NULL CHECK (tax_treatment IN ('taxable', 'tax-advantaged')),
```

with:

```sql
tax_treatment TEXT CHECK (
    tax_treatment IS NULL
    OR tax_treatment IN ('taxable', 'tax-advantaged')
),
```

Make the same source-list update in `holdings_snapshot.source`.

- [ ] **Step 4: Run DB tests**

Run:

```bash
pytest tests/test_db.py -q
```

Expected: PASS. Existing local DB files with old table constraints are not migrated by this plan; manually delete/recreate `accounts` and `holdings_snapshot` before using the feature.

---

## Task 2: Fidelity CSV Parser And Normalizer

**Files:**

- Create: `portfolio/fidelity/__init__.py`
- Create: `portfolio/fidelity/csv.py`
- Create: `tests/test_fidelity_csv.py`

- [ ] **Step 1: Add parser tests and fixtures**

Create `tests/test_fidelity_csv.py`:

```python
from pathlib import Path

import pytest

from portfolio.fidelity.csv import (
    FidelityCsvError,
    discover_accounts,
    normalize_holdings,
    parse_optional_float,
)


CSV_TEXT = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
Z29587187,Trust: Under Agreement,SPAXX**,HELD IN MONEY MARKET,,,,$19324.50,,,,,0.82%,,,Cash
Z29587187,Trust: Under Agreement,IBIT,ISHARES BITCOIN TRUST ETF,236.14,$44.82,-$1.35,$10583.79,-$318.79,-2.93%,-$614.78,-5.49%,0.45%,$11198.57,$47.42,Margin
Z29587187,Trust: Under Agreement,IBIT,ISHARES BITCOIN TRUST ETF,35.757,$44.82,-$1.35,$1602.62,-$48.28,-2.93%,+$2.68,+0.16%,0.07%,$1599.94,$44.74,Cash
12366,NETFLIX401(K),,BROKERAGELINK,363977.42,$1.00,$0.00,$363977.42,$0.00,0.00%,$0.00,0.00%,--,$363977.42,$1.00,
653239878,BrokerageLink,FDRXX**,HELD IN MONEY MARKET,,,,$2044.87,,,,,0.57%,,,Cash

"Date downloaded May-15-2026 5:57 p.m ET"
"""


def _write_csv(tmp_path: Path, content: str = CSV_TEXT) -> Path:
    path = tmp_path / "Portfolio_Positions_May-15-2026.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_discover_accounts_ignores_trailer_rows(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    assert discover_accounts(path) == [
        {"account_id": "12366", "name": "NETFLIX401(K)"},
        {"account_id": "653239878", "name": "BrokerageLink"},
        {"account_id": "Z29587187", "name": "Trust: Under Agreement"},
    ]


def test_parse_optional_float_handles_fidelity_values() -> None:
    assert parse_optional_float("$19,324.50") == 19324.50
    assert parse_optional_float("+$2.68") == 2.68
    assert parse_optional_float("--") is None
    assert parse_optional_float("") is None


def test_normalize_holdings_skips_empty_symbol_and_aggregates_duplicates(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    rows = normalize_holdings(
        path,
        snapshot_date="2026-05-16",
        included_accounts={
            "Z29587187": {"tax_treatment": "taxable"},
            "12366": {"tax_treatment": "tax-advantaged"},
            "653239878": {"tax_treatment": "tax-advantaged"},
        },
    )

    asset_by_key = {(row["account_id"], row["asset_name"]): row for row in rows}
    assert ("12366", "BROKERAGELINK") not in asset_by_key
    assert asset_by_key[("Z29587187", "IBIT")]["value"] == pytest.approx(12186.41)
    assert asset_by_key[("Z29587187", "IBIT")]["quantity"] == pytest.approx(271.897)
    assert asset_by_key[("Z29587187", "SPAXX**")]["is_cash_equivalent"] == 1
    assert asset_by_key[("653239878", "FDRXX**")]["is_cash_equivalent"] == 1


def test_normalize_holdings_ignores_fidelity_type_for_cash_detection(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    rows = normalize_holdings(
        path,
        snapshot_date="2026-05-16",
        included_accounts={"Z29587187": {"tax_treatment": "taxable"}},
    )
    ibit = next(row for row in rows if row["asset_name"] == "IBIT")
    assert ibit["is_cash_equivalent"] == 0


def test_missing_required_header_fails(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "Account Number,Account Name\n1,Account\n")
    with pytest.raises(FidelityCsvError, match="missing required headers"):
        discover_accounts(path)
```

- [ ] **Step 2: Run parser tests and verify they fail**

Run:

```bash
pytest tests/test_fidelity_csv.py -q
```

Expected: FAIL because `portfolio.fidelity.csv` does not exist.

- [ ] **Step 3: Implement `portfolio/fidelity/csv.py`**

Create `portfolio/fidelity/__init__.py` as an empty file.

Create `portfolio/fidelity/csv.py`:

```python
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

REQUIRED_HEADERS = frozenset(
    {
        "Account Number",
        "Account Name",
        "Symbol",
        "Description",
        "Quantity",
        "Last Price",
        "Current Value",
    }
)


class FidelityCsvError(ValueError):
    """Raised when a Fidelity CSV cannot be parsed safely."""


def parse_optional_float(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text or text == "--":
        return None
    text = text.replace("$", "").replace(",", "").replace("%", "")
    if text.startswith("+"):
        text = text[1:]
    return float(text)


def _read_data_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise FidelityCsvError("Fidelity CSV is empty")
        missing = sorted(REQUIRED_HEADERS.difference(reader.fieldnames))
        if missing:
            raise FidelityCsvError(f"Fidelity CSV missing required headers: {', '.join(missing)}")

        rows: list[tuple[int, dict[str, str]]] = []
        for line_number, row in enumerate(reader, start=2):
            account_id = (row.get("Account Number") or "").strip()
            account_name = (row.get("Account Name") or "").strip()
            if not account_id and not account_name:
                break
            if account_id.startswith('"') or account_id.startswith("The data and information"):
                break
            rows.append((line_number, {key: (value or "").strip() for key, value in row.items()}))
        return rows


def discover_accounts(path: Path) -> list[dict[str, str]]:
    accounts: dict[str, str] = {}
    for _, row in _read_data_rows(path):
        account_id = row["Account Number"]
        account_name = row["Account Name"]
        if account_id:
            accounts[account_id] = account_name
    return [
        {"account_id": account_id, "name": name}
        for account_id, name in sorted(accounts.items(), key=lambda item: item[0])
    ]


def _is_cash_equivalent(symbol: str, description: str) -> int:
    normalized_description = description.upper()
    if symbol.endswith("**"):
        return 1
    if "HELD IN MONEY MARKET" in normalized_description:
        return 1
    if "BANK DEPOSIT PORTFOLIO" in normalized_description:
        return 1
    return 0


def _merge(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["value"] = float(existing["value"]) + float(incoming["value"])
    for key in ("quantity",):
        values = [value for value in (existing.get(key), incoming.get(key)) if value is not None]
        existing[key] = sum(float(value) for value in values) if values else None
    if existing.get("quantity"):
        existing["unit_price"] = existing["value"] / existing["quantity"]
    existing["is_cash_equivalent"] = 1 if existing["is_cash_equivalent"] or incoming["is_cash_equivalent"] else 0


def normalize_holdings(
    path: Path,
    *,
    snapshot_date: str,
    included_accounts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    row_by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for line_number, raw in _read_data_rows(path):
        account_id = raw["Account Number"]
        if account_id not in included_accounts:
            continue

        symbol = raw["Symbol"].strip()
        if not symbol:
            continue

        try:
            value = parse_optional_float(raw["Current Value"])
        except ValueError as exc:
            raise FidelityCsvError(
                f"Invalid Current Value at row {line_number} account={account_id} symbol={symbol}"
            ) from exc
        if value is None:
            raise FidelityCsvError(
                f"Missing Current Value at row {line_number} account={account_id} symbol={symbol}"
            )

        description = raw["Description"].strip()
        row = {
            "snapshot_date": snapshot_date,
            "account_id": account_id,
            "source": "fidelity",
            "asset_name": symbol,
            "display_name": description or symbol,
            "plaid_security_id": None,
            "plaid_type": None,
            "plaid_subtype": None,
            "is_cash_equivalent": _is_cash_equivalent(symbol, description),
            "quantity": parse_optional_float(raw["Quantity"]),
            "unit_price": parse_optional_float(raw["Last Price"]),
            "price_as_of": snapshot_date,
            "value": value,
            "bucket": None,
        }
        key = (snapshot_date, account_id, symbol, "fidelity")
        existing = row_by_key.get(key)
        if existing is None:
            row_by_key[key] = row
            rows.append(row)
        else:
            _merge(existing, row)

    return rows
```

- [ ] **Step 4: Run parser tests**

Run:

```bash
pytest tests/test_fidelity_csv.py -q
```

Expected: PASS.

---

## Task 3: Interactive Fidelity Account Setup

**Files:**

- Create: `portfolio/fidelity/accounts.py`
- Create: `tests/test_fidelity_accounts.py`
- Modify: `portfolio/cli.py`

- [ ] **Step 1: Add setup service tests**

Create `tests/test_fidelity_accounts.py`:

```python
from pathlib import Path

from portfolio.db.connection import get_connection, init_db
from portfolio.fidelity.accounts import setup_fidelity_accounts


CSV_TEXT = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
111,Taxable Brokerage,SPY,SPDR S&P 500 ETF,1,$100.00,$0.00,$100.00,$0.00,0.00%,$0.00,0.00%,100.00%,$100.00,$100.00,Margin
222,Roth IRA,SGOV,ISHARES TR 0-3 MNTH TREASRY,1,$100.00,$0.00,$100.00,$0.00,0.00%,$0.00,0.00%,100.00%,$100.00,$100.00,Cash
"""


def _write_csv(tmp_path: Path) -> Path:
    path = tmp_path / "fidelity.csv"
    path.write_text(CSV_TEXT, encoding="utf-8")
    return path


def test_setup_prompts_tax_only_for_included_accounts(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    answers = iter(["y", "taxable", "n"])
    prompts: list[str] = []

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path),
        ask=lambda prompt, default=None: prompts.append(prompt) or next(answers),
    )

    rows = conn.execute(
        "SELECT account_id, source, included, tax_treatment, owner_tag, type, subtype FROM accounts ORDER BY account_id"
    ).fetchall()
    conn.close()

    assert [dict(row) for row in rows] == [
        {
            "account_id": "111",
            "source": "fidelity",
            "included": 1,
            "tax_treatment": "taxable",
            "owner_tag": "household",
            "type": "investment",
            "subtype": None,
        },
        {
            "account_id": "222",
            "source": "fidelity",
            "included": 0,
            "tax_treatment": None,
            "owner_tag": "household",
            "type": "investment",
            "subtype": None,
        },
    ]
    assert len(prompts) == 3


def test_setup_rerun_uses_existing_values_as_defaults(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("111", None, "fidelity", "Taxable Brokerage", "investment", "household", 1, "taxable"),
    )
    conn.commit()
    defaults: list[str | None] = []
    answers = iter(["y", "taxable", "n"])

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path),
        ask=lambda prompt, default=None: defaults.append(default) or next(answers),
    )

    conn.close()
    assert defaults[:2] == ["y", "taxable"]
```

- [ ] **Step 2: Run setup tests and verify they fail**

Run:

```bash
pytest tests/test_fidelity_accounts.py -q
```

Expected: FAIL because `portfolio.fidelity.accounts` does not exist.

- [ ] **Step 3: Implement account setup service**

Create `portfolio/fidelity/accounts.py`:

```python
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

from portfolio.fidelity.csv import discover_accounts

AskFn = Callable[[str, str | None], str]


def _normalize_yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"y", "yes"}:
        return True
    if normalized in {"n", "no"}:
        return False
    raise ValueError("Please answer y or n")


def _normalize_tax_treatment(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"taxable", "tax-advantaged"}:
        return normalized
    raise ValueError("Tax treatment must be taxable or tax-advantaged")


def setup_fidelity_accounts(conn: sqlite3.Connection, csv_path: Path, *, ask: AskFn) -> int:
    count = 0
    for account in discover_accounts(csv_path):
        account_id = account["account_id"]
        existing = conn.execute(
            "SELECT included, tax_treatment FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        include_default = "y" if existing is not None and existing["included"] else "n"
        include_answer = ask(
            f"Include Fidelity account {account_id} ({account['name']}) in snapshots? [y/n]",
            include_default,
        )
        included = _normalize_yes_no(include_answer or include_default)

        tax_treatment: str | None = None
        if included:
            tax_default = (
                str(existing["tax_treatment"])
                if existing is not None and existing["tax_treatment"] is not None
                else "taxable"
            )
            tax_answer = ask(
                f"Tax treatment for {account_id} ({account['name']})? [taxable/tax-advantaged]",
                tax_default,
            )
            tax_treatment = _normalize_tax_treatment(tax_answer or tax_default)

        conn.execute(
            """
            INSERT INTO accounts (
                account_id, item_id, source, name, type, subtype, owner_tag,
                included, tax_treatment, tax_treatment_override
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                source = excluded.source,
                name = excluded.name,
                type = excluded.type,
                subtype = excluded.subtype,
                owner_tag = COALESCE(accounts.owner_tag, excluded.owner_tag),
                included = excluded.included,
                tax_treatment = excluded.tax_treatment,
                tax_treatment_override = excluded.tax_treatment_override
            """,
            (
                account_id,
                None,
                "fidelity",
                account["name"],
                "investment",
                None,
                "household",
                1 if included else 0,
                tax_treatment,
                tax_treatment,
            ),
        )
        count += 1
    conn.commit()
    return count
```

- [ ] **Step 4: Add Typer command**

In `portfolio/cli.py`, add imports:

```python
from pathlib import Path
from portfolio.fidelity.accounts import setup_fidelity_accounts
```

Add a Typer app:

```python
fidelity_app = typer.Typer(help="Manage Fidelity CSV accounts")
```

Add the command:

```python
@fidelity_app.command("setup")
def fidelity_setup(csv_path: Path = typer.Option(..., "--csv", exists=True, readable=True)) -> None:
    """Discover and configure Fidelity accounts from a positions CSV."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)

        def ask(prompt: str, default: str | None = None) -> str:
            suffix = f" (default: {default})" if default is not None else ""
            value = typer.prompt(f"{prompt}{suffix}", default=default or "", show_default=False)
            return str(value)

        count = setup_fidelity_accounts(conn, csv_path, ask=ask)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        conn.close()
    typer.echo(f"Configured {count} Fidelity account(s)")
```

Register it near the existing managed app registration:

```python
app.add_typer(fidelity_app, name="fidelity")
```

- [ ] **Step 5: Run setup tests**

Run:

```bash
pytest tests/test_fidelity_accounts.py -q
```

Expected: PASS.

---

## Task 4: Snapshot Integration

**Files:**

- Modify: `portfolio/snapshot/runner.py`
- Modify: `portfolio/cli.py`
- Modify: `tests/test_fidelity_csv.py`

- [ ] **Step 1: Add validation tests for snapshot import inputs**

Append to `tests/test_fidelity_csv.py`:

```python
from portfolio.fidelity.csv import validate_snapshot_accounts


def test_validate_snapshot_accounts_rejects_missing_setup(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    with pytest.raises(FidelityCsvError, match="not set up"):
        validate_snapshot_accounts(path, configured_accounts={})


def test_validate_snapshot_accounts_rejects_included_null_tax(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    with pytest.raises(FidelityCsvError, match="tax treatment"):
        validate_snapshot_accounts(
            path,
            configured_accounts={"Z29587187": {"included": 1, "tax_treatment": None}},
        )
```

- [ ] **Step 2: Implement validation helper**

In `portfolio/fidelity/csv.py`, add:

```python
def validate_snapshot_accounts(
    path: Path,
    *,
    configured_accounts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    csv_account_ids = {account["account_id"] for account in discover_accounts(path)}
    missing = sorted(account_id for account_id in csv_account_ids if account_id not in configured_accounts)
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
        account_id for account_id, account in included.items() if account.get("tax_treatment") is None
    )
    if missing_tax:
        raise FidelityCsvError(
            "Included Fidelity accounts missing tax treatment: " + ", ".join(missing_tax)
        )
    return included
```

- [ ] **Step 3: Run Fidelity CSV tests**

Run:

```bash
pytest tests/test_fidelity_csv.py -q
```

Expected: PASS.

- [ ] **Step 4: Wire Fidelity rows into snapshot runner**

In `portfolio/snapshot/runner.py`, import:

```python
from pathlib import Path
from portfolio.fidelity.csv import normalize_holdings as normalize_fidelity_holdings
from portfolio.fidelity.csv import validate_snapshot_accounts
```

Change the function signature:

```python
def run_snapshot(
    conn: sqlite3.Connection,
    settings: Settings,
    snapshot_date: str | None = None,
    *,
    fidelity_csv: Path | None = None,
) -> dict[str, Any]:
```

After Plaid rows are built and before managed rows:

```python
    fidelity_rows: list[dict[str, Any]] = []
    if fidelity_csv is not None:
        configured = {
            str(row["account_id"]): {
                "included": row["included"],
                "tax_treatment": row["tax_treatment"],
            }
            for row in conn.execute(
                """
                SELECT account_id, included, tax_treatment
                FROM accounts
                WHERE source = 'fidelity'
                """
            ).fetchall()
        }
        included = validate_snapshot_accounts(fidelity_csv, configured_accounts=configured)
        fidelity_rows = normalize_fidelity_holdings(
            fidelity_csv,
            snapshot_date=target_date,
            included_accounts=included,
        )

    managed_rows = materialize_managed_rows(conn, target_date)
    insert_holdings_snapshot(conn, plaid_rows + fidelity_rows + managed_rows)
```

Update the return count:

```python
"holdings_count": len(plaid_rows) + len(fidelity_rows) + len(managed_rows),
```

- [ ] **Step 5: Add CLI option**

In `portfolio/cli.py`, update `snapshot()`:

```python
def snapshot(
    snapshot_date: str | None = typer.Option(
        None,
        "--snapshot-date",
        help="ISO date; defaults to today",
    ),
    fidelity_csv: Path | None = typer.Option(
        None,
        "--fidelity-csv",
        exists=True,
        readable=True,
        help="Optional Fidelity positions CSV to include in the snapshot",
    ),
) -> None:
```

Pass the option:

```python
result = run_snapshot(conn, settings, snapshot_date=snapshot_date, fidelity_csv=fidelity_csv)
```

- [ ] **Step 6: Run focused snapshot-related tests**

Run:

```bash
pytest tests/test_fidelity_csv.py tests/test_fidelity_accounts.py tests/test_db.py -q
```

Expected: PASS.

---

## Task 5: Account Queries And Export Compatibility

**Files:**

- Modify: `portfolio/db/queries.py`
- Modify: `tests/test_export_csv.py`

- [ ] **Step 1: Add export test for Fidelity detail rows**

Append to `tests/test_export_csv.py`:

```python
def test_export_snapshot_csv_includes_fidelity_source(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("fid-1", None, "fidelity", "Fidelity Brokerage", "investment", "household", 1, "taxable"),
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name, value, bucket
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-16", "fid-1", "fidelity", "SPY", "SPDR S&P 500 ETF", 1000, "Equity"),
    )
    conn.execute(
        """
        INSERT INTO snapshot_summary (snapshot_date, bucket, tax_treatment, owner_tag, total_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("2026-05-16", "Equity", "taxable", "household", 1000),
    )
    conn.commit()

    out_path = tmp_path / "snapshot.csv"
    export_snapshot_csv(conn, "2026-05-16", out_path)
    content = out_path.read_text()

    assert "Fidelity Brokerage,SPY,Equity,1000.0,taxable,household,fidelity" in content
```

- [ ] **Step 2: Adjust account update validation only if needed**

Review `portfolio/db/queries.py`. Keep `update_account()` validation strict for user-provided tax treatment:

```python
if tax_treatment is not None:
    if tax_treatment not in {"taxable", "tax-advantaged"}:
        raise ValueError("tax_treatment must be 'taxable' or 'tax-advantaged'")
```

No change is needed unless tests show account listing or updates assume tax treatment is always non-null.

- [ ] **Step 3: Run export and account tests**

Run:

```bash
pytest tests/test_export_csv.py tests/test_plaid_accounts.py -q
```

Expected: PASS.

---

## Task 6: Documentation And Final Verification

**Files:**

- Modify: `README.md`
- Optional modify: `.gitignore`

- [ ] **Step 1: Document Fidelity CSV commands**

In `README.md`, add a short section near the snapshot/account preference docs:

````markdown
## Fidelity CSV accounts

Fidelity accounts that are not available through Plaid can be imported from a downloaded positions CSV.

First configure accounts from the CSV:

```bash
portfolio fidelity setup --csv snapshots/Portfolio_Positions_May-15-2026.csv
```

For each account, the setup flow asks whether to include it. Included accounts also require a tax treatment: `taxable` or `tax-advantaged`. Owner tags default to `household`.

Then include the CSV during a snapshot:

```bash
portfolio snapshot --fidelity-csv snapshots/Portfolio_Positions_May-15-2026.csv
```

Rows with an empty `Symbol` are ignored, and the Fidelity `Type` column is ignored because it describes margin eligibility rather than asset type.
````

- [ ] **Step 2: Ensure raw input CSVs are ignored**

Check `.gitignore`. If `snapshots/` or `snapshots/*.csv` is not ignored, add an ignore rule that prevents downloaded Fidelity CSVs from being committed while preserving tracked docs/tests.

- [ ] **Step 3: Run focused tests**

Run:

```bash
pytest tests/test_fidelity_csv.py tests/test_fidelity_accounts.py tests/test_db.py tests/test_export_csv.py -q
```

Expected: PASS.

- [ ] **Step 4: Run the full suite**

Run:

```bash
pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit implementation**

Commit only the implementation files for this feature:

```bash
git add portfolio/fidelity portfolio/db/schema.sql portfolio/db/queries.py portfolio/snapshot/runner.py portfolio/cli.py tests/test_fidelity_csv.py tests/test_fidelity_accounts.py tests/test_db.py tests/test_export_csv.py README.md .gitignore
git commit -m "$(cat <<'EOF'
Add Fidelity CSV snapshot import

EOF
)"
```

---

## Self-Review

- **Spec coverage:** The tasks cover interactive setup, no subtype inference, nullable tax treatment for excluded accounts, Fidelity source schema support without automated migration, optional snapshot CSV ingestion, empty-symbol row skipping, ignoring `Type`, cash detection, duplicate aggregation, validation errors, docs, and tests.
- **Placeholder scan:** No placeholder tasks remain; every implementation step names files, expected behavior, and verification commands.
- **Type consistency:** Plan consistently uses `source='fidelity'`, `tax_treatment` nullable in `accounts`, `snapshot --fidelity-csv`, and `portfolio fidelity setup --csv`.

# Fidelity Setup Prompt UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the ambiguous two-step Fidelity account setup prompts with one self-documenting menu per account.

**Architecture:** Keep the prompt orchestration in `portfolio/fidelity/accounts.py`, because that module already owns discovered Fidelity account preferences and database persistence. Add small parsing/default helpers that map user menu input into `(included, tax_treatment)` state, then keep the existing database upsert behavior unchanged. Cover the behavior with focused tests in a new `tests/test_fidelity_accounts.py`.

**Tech Stack:** Python 3.12, Typer prompt adapter, SQLite, pytest.

---

## File Structure

- Modify: `tests/test_fidelity_accounts.py` - preserve existing setup/collision coverage and update/add focused tests for menu choices, aliases, defaults, and validation.
- Modify: `portfolio/fidelity/accounts.py` - replace the include/tax free-text prompt flow with one menu prompt and helper functions.
- No change expected: `portfolio/cli.py` - the existing `ask(prompt, default)` adapter can display a multiline prompt through `typer.prompt`.

Do not commit unless the user explicitly asks for a commit.

---

## Task 1: Update Prompt UX Tests

**Files:**

- Modify: `tests/test_fidelity_accounts.py`

- [ ] **Step 1: Update existing setup prompt tests**

Do not rewrite the whole file. `tests/test_fidelity_accounts.py` already exists and contains valuable coverage for persistence, saved defaults, account ID collisions, and collision pre-scanning. Keep those tests, but update the tests that assume the old two-prompt flow.

Use the following code as reference snippets to integrate into the existing file, not as complete file content. Reuse the existing `CSV_TEXT`, `_write_csv()`, collision tests, and imports where practical. Replace the old prompt-flow tests (`test_setup_prompts_tax_only_for_included_accounts`, `test_setup_rerun_uses_existing_values_as_defaults`, `test_setup_blank_answers_use_defaults_for_existing_account`, and `test_setup_blank_tax_answer_uses_taxable_default_for_new_account`) with menu-choice equivalents, and add the helper functions only if they make the updated tests clearer:

```python
from pathlib import Path
from typing import Callable

import pytest

from portfolio.db.connection import get_connection, init_db
from portfolio.fidelity.accounts import setup_fidelity_accounts


CSV_HEADER = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Current Value\n"
)


def _write_csv(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    body = "".join(
        f"{account_id},{account_name},SPY,SPDR S&P 500 ETF,1,$100.00,$100.00\n"
        for account_id, account_name in rows
    )
    path = tmp_path / "Portfolio_Positions.csv"
    path.write_text(CSV_HEADER + body, encoding="utf-8")
    return path


def _run_setup(
    tmp_path: Path,
    answers: list[str],
    *,
    before_setup: Callable | None = None,
) -> tuple[list[tuple[str, str | None]], object]:
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    if before_setup is not None:
        before_setup(conn)

    prompts: list[tuple[str, str | None]] = []
    answer_iter = iter(answers)

    def ask(prompt: str, default: str | None = None) -> str:
        prompts.append((prompt, default))
        return next(answer_iter)

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, [("12366", "NETFLIX401(K)")]),
        ask=ask,
    )
    return prompts, conn


def _account_row(conn: object) -> dict:
    row = conn.execute(
        """
        SELECT included, tax_treatment, tax_treatment_override
        FROM accounts
        WHERE account_id = ?
        """,
        ("12366",),
    ).fetchone()
    assert row is not None
    return dict(row)


def test_choice_1_includes_account_as_taxable(tmp_path: Path) -> None:
    prompts, conn = _run_setup(tmp_path, ["1"])

    assert prompts == [
        (
            "Fidelity account NETFLIX401(K) (12366)\n"
            "  1) Include as taxable\n"
            "  2) Include as tax-advantaged\n"
            "  3) Exclude from snapshots\n"
            "Choose",
            "1",
        )
    ]
    assert _account_row(conn) == {
        "included": 1,
        "tax_treatment": "taxable",
        "tax_treatment_override": "taxable",
    }
    conn.close()


def test_choice_2_includes_account_as_tax_advantaged(tmp_path: Path) -> None:
    _, conn = _run_setup(tmp_path, ["2"])

    assert _account_row(conn) == {
        "included": 1,
        "tax_treatment": "tax-advantaged",
        "tax_treatment_override": "tax-advantaged",
    }
    conn.close()


def test_choice_3_excludes_account_without_tax_fields(tmp_path: Path) -> None:
    _, conn = _run_setup(tmp_path, ["3"])

    assert _account_row(conn) == {
        "included": 0,
        "tax_treatment": None,
        "tax_treatment_override": None,
    }
    conn.close()


@pytest.mark.parametrize(
    ("answer", "expected_tax_treatment"),
    [
        ("t", "taxable"),
        ("taxable", "taxable"),
        ("a", "tax-advantaged"),
        ("advantaged", "tax-advantaged"),
        ("tax-advantaged", "tax-advantaged"),
    ],
)
def test_choice_aliases_include_account(
    tmp_path: Path,
    answer: str,
    expected_tax_treatment: str,
) -> None:
    _, conn = _run_setup(tmp_path, [answer])

    assert _account_row(conn) == {
        "included": 1,
        "tax_treatment": expected_tax_treatment,
        "tax_treatment_override": expected_tax_treatment,
    }
    conn.close()


@pytest.mark.parametrize("answer", ["n", "no", "exclude", "excluded"])
def test_exclude_aliases_exclude_account(tmp_path: Path, answer: str) -> None:
    _, conn = _run_setup(tmp_path, [answer])

    assert _account_row(conn) == {
        "included": 0,
        "tax_treatment": None,
        "tax_treatment_override": None,
    }
    conn.close()


def test_empty_choice_uses_existing_tax_advantaged_default(tmp_path: Path) -> None:
    def seed_existing(conn: object) -> None:
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, item_id, source, name, type, subtype, owner_tag,
                included, tax_treatment, tax_treatment_override
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "12366",
                None,
                "fidelity",
                "NETFLIX401(K)",
                "investment",
                None,
                "household",
                1,
                "tax-advantaged",
                "tax-advantaged",
            ),
        )

    prompts, conn = _run_setup(tmp_path, [""], before_setup=seed_existing)

    assert prompts[0][1] == "2"
    assert _account_row(conn) == {
        "included": 1,
        "tax_treatment": "tax-advantaged",
        "tax_treatment_override": "tax-advantaged",
    }
    conn.close()


def test_empty_choice_uses_existing_excluded_default(tmp_path: Path) -> None:
    def seed_existing(conn: object) -> None:
        conn.execute(
            """
            INSERT INTO accounts (
                account_id, item_id, source, name, type, subtype, owner_tag,
                included, tax_treatment, tax_treatment_override
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "12366",
                None,
                "fidelity",
                "NETFLIX401(K)",
                "investment",
                None,
                "household",
                0,
                None,
                None,
            ),
        )

    prompts, conn = _run_setup(tmp_path, [""], before_setup=seed_existing)

    assert prompts[0][1] == "3"
    assert _account_row(conn) == {
        "included": 0,
        "tax_treatment": None,
        "tax_treatment_override": None,
    }
    conn.close()


def test_invalid_choice_fails_with_allowed_options(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="choose 1, 2, 3, t, a, or n"):
        _run_setup(tmp_path, ["x"])
```

- [ ] **Step 2: Run tests and verify they fail for the current implementation**

Run:

```bash
pytest tests/test_fidelity_accounts.py -q
```

Expected: FAIL. The current implementation treats `1`, `2`, and `3` as invalid yes/no answers, uses the old prompt labels, and has no single-menu parser.

---

## Task 2: Add Choice Parser And Defaults

**Files:**

- Modify: `portfolio/fidelity/accounts.py`

- [ ] **Step 1: Add parser/default helpers**

In `portfolio/fidelity/accounts.py`, replace the helper section starting at `_include_default` with:

```python
def _choice_prompt(account: dict[str, str]) -> str:
    return (
        f"Fidelity account {account['name']} ({account['account_id']})\n"
        "  1) Include as taxable\n"
        "  2) Include as tax-advantaged\n"
        "  3) Exclude from snapshots\n"
        "Choose"
    )


def _choice_default(existing: sqlite3.Row | None) -> str:
    if existing is None:
        return "1"
    if not existing["included"]:
        return "3"
    tax_treatment = _tax_default(existing)
    if tax_treatment == "tax-advantaged":
        return "2"
    return "1"


def _answer_or_default(value: str, default: str | None) -> str:
    if value.strip():
        return value
    if default is not None:
        return default
    return value


def _normalize_account_choice(value: str) -> tuple[bool, str | None]:
    normalized = value.strip().lower()
    if normalized in {"1", "t", "taxable"}:
        return True, "taxable"
    if normalized in {"2", "a", "advantaged", "tax-advantaged"}:
        return True, "tax-advantaged"
    if normalized in {"3", "n", "no", "exclude", "excluded"}:
        return False, None
    raise ValueError("choose 1, 2, 3, t, a, or n")


def _tax_default(existing: sqlite3.Row | None) -> str | None:
    if existing is None:
        return "taxable"
    return existing["tax_treatment_override"] or existing["tax_treatment"]
```

Remove the old `_include_default`, `_normalize_yes_no`, and `_normalize_tax_treatment` helpers after adding the new helpers. They will no longer be used.

- [ ] **Step 2: Run focused tests and verify expected remaining failures**

Run:

```bash
pytest tests/test_fidelity_accounts.py -q
```

Expected: still FAIL, because `setup_fidelity_accounts()` still calls the old include/tax prompts and does not use `_normalize_account_choice()` yet.

---

## Task 3: Replace The Two Prompts With One Menu

**Files:**

- Modify: `portfolio/fidelity/accounts.py`

- [ ] **Step 1: Replace the prompt block inside `setup_fidelity_accounts()`**

In `setup_fidelity_accounts()`, replace this block:

```python
        include_default = _include_default(existing)
        included = _normalize_yes_no(
            _answer_or_default(
                ask(f"Include Fidelity account {account['name']} ({account_id})?", include_default),
                include_default,
            )
        )

        tax_treatment = None
        tax_treatment_override = None
        if included:
            tax_default = _tax_default(existing)
            tax_treatment = _normalize_tax_treatment(
                _answer_or_default(
                    ask(f"Tax treatment for Fidelity account {account['name']} ({account_id})?", tax_default),
                    tax_default,
                )
            )
            tax_treatment_override = tax_treatment
```

with:

```python
        choice_default = _choice_default(existing)
        included, tax_treatment = _normalize_account_choice(
            _answer_or_default(
                ask(_choice_prompt(account), choice_default),
                choice_default,
            )
        )
        tax_treatment_override = tax_treatment if included else None
```

This preserves the existing upsert behavior below the prompt block:

- included taxable -> `included=1`, `tax_treatment='taxable'`, `tax_treatment_override='taxable'`
- included tax-advantaged -> `included=1`, `tax_treatment='tax-advantaged'`, `tax_treatment_override='tax-advantaged'`
- excluded -> `included=0`, `tax_treatment=NULL`, `tax_treatment_override=NULL`

- [ ] **Step 2: Run focused tests and verify they pass**

Run:

```bash
pytest tests/test_fidelity_accounts.py -q
```

Expected: PASS.

---

## Task 4: Verify CLI Registration Still Works

**Files:**

- Test: `tests/test_cli.py`
- Test: `tests/test_fidelity_accounts.py`

- [ ] **Step 1: Run CLI and Fidelity setup tests together**

Run:

```bash
pytest tests/test_cli.py tests/test_fidelity_accounts.py -q
```

Expected: PASS. `tests/test_cli.py` should still confirm the `fidelity` command group is registered, and the new tests should confirm the prompt UX.

- [ ] **Step 2: Check lints for edited Python files**

Use Cursor diagnostics or run the project linter if one is configured. If using Cursor diagnostics, check:

- `portfolio/fidelity/accounts.py`
- `tests/test_fidelity_accounts.py`

Expected: no new lint errors.

---

## Task 5: Final Verification

**Files:**

- Test: `tests/test_fidelity_accounts.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Run the focused verification command**

Run:

```bash
pytest tests/test_fidelity_accounts.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 2: Optionally run the full suite if this branch is otherwise stable**

Run:

```bash
pytest -q
```

Expected: PASS, unless unrelated in-progress branch work already has failing tests. If unrelated failures appear, record them separately and do not change unrelated files.

---

## Self-Review

- **Spec coverage:** The plan implements the approved single-menu design, preserves saved defaults, accepts one-letter and numbered choices, supports exclusion, and keeps excluded accounts with null tax fields.
- **Placeholder scan:** No TODO, TBD, or vague implementation steps remain.
- **Type consistency:** Helper signatures match existing `AskFn`, `sqlite3.Row`, and account dictionaries returned by `discover_accounts()`.

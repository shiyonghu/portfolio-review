from pathlib import Path

import pytest

from portfolio.db.connection import get_connection, init_db
from portfolio.fidelity.accounts import setup_fidelity_accounts


CSV_TEXT = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
111,Taxable Brokerage,SPY,SPDR S&P 500 ETF,1,$100.00,$0.00,$100.00,$0.00,0.00%,$0.00,0.00%,100.00%,$100.00,$100.00,Margin
222,Roth IRA,SGOV,ISHARES TR 0-3 MNTH TREASRY,1,$100.00,$0.00,$100.00,$0.00,0.00%,$0.00,0.00%,100.00%,$100.00,$100.00,Cash
"""


def _write_csv(tmp_path: Path, content: str = CSV_TEXT) -> Path:
    path = tmp_path / "fidelity.csv"
    path.write_text(content, encoding="utf-8")
    return path


EXPECTED_FIRST_ACCOUNT_PROMPT = """Fidelity account NETFLIX401(K) (12366)
  1) Include as taxable
  2) Include as tax-advantaged
  3) Exclude from snapshots
Choose"""


SINGLE_ACCOUNT_CSV_TEXT = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
12366,NETFLIX401(K),NFLX,NETFLIX INC,1,$100.00,$0.00,$100.00,$0.00,0.00%,$0.00,0.00%,100.00%,$100.00,$100.00,Cash
"""


def _row_for_account(conn, account_id: str = "12366") -> dict:
    row = conn.execute(
        """
        SELECT account_id, source, included, tax_treatment, tax_treatment_override, owner_tag, type, subtype
        FROM accounts
        WHERE account_id = ?
        """,
        (account_id,),
    ).fetchone()
    return dict(row)


def _expected_account_row(
    *,
    included: int,
    tax_treatment: str | None,
    account_id: str = "12366",
) -> dict:
    return {
        "account_id": account_id,
        "source": "fidelity",
        "included": included,
        "tax_treatment": tax_treatment,
        "tax_treatment_override": tax_treatment,
        "owner_tag": "household",
        "type": "investment",
        "subtype": None,
    }


def test_setup_choice_1_includes_account_as_taxable_with_menu_default(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    prompts: list[tuple[str, str | None]] = []

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
        ask=lambda prompt, default=None: prompts.append((prompt, default)) or "1",
    )

    row = _row_for_account(conn)
    conn.close()

    assert row == _expected_account_row(included=1, tax_treatment="taxable")
    assert prompts == [(EXPECTED_FIRST_ACCOUNT_PROMPT, "1")]


def test_setup_choice_2_includes_account_as_tax_advantaged(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
        ask=lambda prompt, default=None: "2",
    )

    row = _row_for_account(conn)
    conn.close()

    assert row == _expected_account_row(included=1, tax_treatment="tax-advantaged")


def test_setup_choice_3_excludes_account_and_stores_null_tax_fields(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
        ask=lambda prompt, default=None: "3",
    )

    row = _row_for_account(conn)
    conn.close()

    assert row == _expected_account_row(included=0, tax_treatment=None)


@pytest.mark.parametrize(
    ("answer", "included", "tax_treatment"),
    [
        ("t", 1, "taxable"),
        ("taxable", 1, "taxable"),
        ("a", 1, "tax-advantaged"),
        ("advantaged", 1, "tax-advantaged"),
        ("tax-advantaged", 1, "tax-advantaged"),
        ("n", 0, None),
        ("no", 0, None),
        ("exclude", 0, None),
        ("excluded", 0, None),
    ],
)
def test_setup_accepts_menu_aliases(
    tmp_path: Path,
    answer: str,
    included: int,
    tax_treatment: str | None,
) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
        ask=lambda prompt, default=None: answer,
    )

    row = _row_for_account(conn)
    conn.close()

    assert row == _expected_account_row(included=included, tax_treatment=tax_treatment)


def test_setup_empty_input_uses_existing_tax_advantaged_default(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("12366", None, "fidelity", "NETFLIX401(K)", "investment", "household", 1, "tax-advantaged"),
    )
    conn.commit()
    defaults: list[str | None] = []

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
        ask=lambda prompt, default=None: defaults.append(default) or "",
    )

    row = _row_for_account(conn)
    conn.close()

    assert row == _expected_account_row(included=1, tax_treatment="tax-advantaged")
    assert defaults == ["2"]


def test_setup_empty_input_uses_existing_excluded_default(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("12366", None, "fidelity", "NETFLIX401(K)", "investment", "household", 0, None),
    )
    conn.commit()
    defaults: list[str | None] = []

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
        ask=lambda prompt, default=None: defaults.append(default) or "",
    )

    row = _row_for_account(conn)
    conn.close()

    assert row == _expected_account_row(included=0, tax_treatment=None)
    assert defaults == ["3"]


def test_setup_invalid_menu_choice_raises_value_error(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    with pytest.raises(ValueError, match="choose 1, 2, 3, t, a, or n"):
        setup_fidelity_accounts(
            conn,
            _write_csv(tmp_path, SINGLE_ACCOUNT_CSV_TEXT),
            ask=lambda prompt, default=None: "bogus",
        )

    conn.close()


def test_setup_rejects_account_id_collision_with_non_fidelity_source(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("111", None, "plaid", "Plaid Brokerage", "investment", "household", 1, "taxable"),
    )
    conn.commit()

    with pytest.raises(ValueError, match="111.*plaid"):
        setup_fidelity_accounts(
            conn,
            _write_csv(tmp_path),
            ask=lambda prompt, default=None: "y",
        )

    row = conn.execute(
        "SELECT source, name FROM accounts WHERE account_id = ?",
        ("111",),
    ).fetchone()
    conn.close()

    assert dict(row) == {"source": "plaid", "name": "Plaid Brokerage"}


def test_setup_prescans_collisions_before_making_changes(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("222", None, "plaid", "Plaid IRA", "investment", "household", 1, "tax-advantaged"),
    )
    conn.commit()
    prompts: list[str] = []
    answers = iter(["y", "taxable"])

    with pytest.raises(ValueError, match="222.*plaid"):
        setup_fidelity_accounts(
            conn,
            _write_csv(tmp_path),
            ask=lambda prompt, default=None: prompts.append(prompt) or next(answers),
        )

    rows = conn.execute(
        "SELECT account_id, source FROM accounts ORDER BY account_id",
    ).fetchall()
    conn.close()

    assert prompts == []
    assert [dict(row) for row in rows] == [{"account_id": "222", "source": "plaid"}]

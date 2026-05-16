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
        """
        SELECT account_id, source, included, tax_treatment, tax_treatment_override, owner_tag, type, subtype
        FROM accounts
        ORDER BY account_id
        """
    ).fetchall()
    conn.close()

    assert [dict(row) for row in rows] == [
        {
            "account_id": "111",
            "source": "fidelity",
            "included": 1,
            "tax_treatment": "taxable",
            "tax_treatment_override": "taxable",
            "owner_tag": "household",
            "type": "investment",
            "subtype": None,
        },
        {
            "account_id": "222",
            "source": "fidelity",
            "included": 0,
            "tax_treatment": None,
            "tax_treatment_override": None,
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


def test_setup_blank_answers_use_defaults_for_existing_account(tmp_path: Path) -> None:
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
    answers = iter(["", "   ", "n"])

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path),
        ask=lambda prompt, default=None: next(answers),
    )

    row = conn.execute(
        "SELECT included, tax_treatment FROM accounts WHERE account_id = ?",
        ("111",),
    ).fetchone()
    conn.close()

    assert dict(row) == {"included": 1, "tax_treatment": "taxable"}


def test_setup_blank_tax_answer_uses_taxable_default_for_new_account(tmp_path: Path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    answers = iter(["y", "", "n"])

    setup_fidelity_accounts(
        conn,
        _write_csv(tmp_path),
        ask=lambda prompt, default=None: next(answers),
    )

    row = conn.execute(
        "SELECT included, tax_treatment FROM accounts WHERE account_id = ?",
        ("111",),
    ).fetchone()
    conn.close()

    assert dict(row) == {"included": 1, "tax_treatment": "taxable"}


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

from pathlib import Path

import pytest
import typer

from portfolio import cli
from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db
from portfolio.fidelity.csv import (
    FidelityCsvError,
    discover_accounts,
    normalize_holdings,
    parse_optional_float,
    validate_snapshot_accounts,
)
from portfolio.snapshot import runner as snapshot_runner
from portfolio.snapshot.runner import run_snapshot


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


def _settings(tmp_path: Path) -> Settings:
    return Settings("", "", "sandbox", str(tmp_path / "portfolio.db"), "http://localhost:11434", "llama3.1")


def test_discover_accounts_ignores_trailer_rows(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    assert discover_accounts(path) == [
        {"account_id": "12366", "name": "NETFLIX401(K)"},
        {"account_id": "653239878", "name": "BrokerageLink"},
        {"account_id": "Z29587187", "name": "Trust: Under Agreement"},
    ]


def test_discover_accounts_keeps_distinct_account_number_name_pairs(tmp_path: Path) -> None:
    csv_text = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value
12345,Original Account,VTI,Vanguard Total Stock Market ETF,1,$250.00,$250.00
12345,Renamed Account,VXUS,Vanguard Total International Stock ETF,2,$60.00,$120.00
"""
    path = _write_csv(tmp_path, csv_text)

    assert discover_accounts(path) == [
        {"account_id": "12345", "name": "Original Account"},
        {"account_id": "12345", "name": "Renamed Account"},
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
    assert asset_by_key[("Z29587187", "IBIT")]["price_as_of"] == "2026-05-16"


def test_normalize_holdings_ignores_fidelity_type_for_cash_detection(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    rows = normalize_holdings(
        path,
        snapshot_date="2026-05-16",
        included_accounts={"Z29587187": {"tax_treatment": "taxable"}},
    )
    ibit = next(row for row in rows if row["asset_name"] == "IBIT")
    assert ibit["is_cash_equivalent"] == 0


def test_normalize_holdings_stops_at_disclaimer_without_blank_separator(tmp_path: Path) -> None:
    csv_text = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value
Z29587187,Trust: Under Agreement,IBIT,ISHARES BITCOIN TRUST ETF,1,$44.82,$44.82
"The data and information in this spreadsheet is provided for informational purposes only"
Z29587187,Trust: Under Agreement,VTI,Vanguard Total Stock Market ETF,1,$250.00,$250.00
"""
    path = _write_csv(tmp_path, csv_text)

    rows = normalize_holdings(
        path,
        snapshot_date="2026-05-16",
        included_accounts={"Z29587187": {"tax_treatment": "taxable"}},
    )

    assert len(rows) == 1
    assert rows[0]["asset_name"] == "IBIT"


@pytest.mark.parametrize("current_value", ["", "--"])
def test_normalize_holdings_requires_current_value(tmp_path: Path, current_value: str) -> None:
    csv_text = f"""Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value
Z29587187,Trust: Under Agreement,VTI,Vanguard Total Stock Market ETF,1,$250.00,{current_value}
"""
    path = _write_csv(tmp_path, csv_text)

    with pytest.raises(FidelityCsvError, match=r"row 2.*Z29587187.*VTI.*Current Value"):
        normalize_holdings(
            path,
            snapshot_date="2026-05-16",
            included_accounts={"Z29587187": {"tax_treatment": "taxable"}},
        )


def test_normalize_holdings_parse_errors_include_row_context(tmp_path: Path) -> None:
    csv_text = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value
Z29587187,Trust: Under Agreement,VTI,Vanguard Total Stock Market ETF,1,$250.00,not-a-number
"""
    path = _write_csv(tmp_path, csv_text)

    with pytest.raises(
        FidelityCsvError,
        match=r"row 2.*Z29587187.*VTI.*Current Value.*not-a-number",
    ):
        normalize_holdings(
            path,
            snapshot_date="2026-05-16",
            included_accounts={"Z29587187": {"tax_treatment": "taxable"}},
        )


def test_missing_required_header_fails(tmp_path: Path) -> None:
    path = _write_csv(tmp_path, "Account Number,Account Name\n1,Account\n")
    with pytest.raises(FidelityCsvError, match="missing required headers"):
        discover_accounts(path)


def test_validate_snapshot_accounts_rejects_missing_setup(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    with pytest.raises(FidelityCsvError, match="not set up"):
        validate_snapshot_accounts(path, configured_accounts={})


def test_validate_snapshot_accounts_rejects_included_null_tax(tmp_path: Path) -> None:
    path = _write_csv(tmp_path)
    with pytest.raises(FidelityCsvError, match="tax treatment"):
        validate_snapshot_accounts(
            path,
            configured_accounts={
                "12366": {"included": 0, "tax_treatment": None},
                "653239878": {"included": 0, "tax_treatment": None},
                "Z29587187": {"included": 1, "tax_treatment": None},
            },
        )


def test_run_snapshot_includes_validated_fidelity_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.executemany(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("12366", None, "fidelity", "NETFLIX401(K)", "investment", "household", 0, None),
            ("653239878", None, "fidelity", "BrokerageLink", "investment", "household", 0, None),
            ("Z29587187", None, "fidelity", "Trust: Under Agreement", "investment", "household", 1, "taxable"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO classifications (asset_name, bucket, source, classified_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        [("IBIT", "Crypto", "rule"), ("SPAXX**", "Cash", "rule")],
    )
    conn.commit()

    result = run_snapshot(
        conn,
        _settings(tmp_path),
        snapshot_date="2026-05-16",
        fidelity_csv=_write_csv(tmp_path),
    )

    rows = conn.execute(
        """
        SELECT account_id, source, asset_name, value
        FROM holdings_snapshot
        ORDER BY account_id, asset_name
        """
    ).fetchall()
    conn.close()

    assert result["holdings_count"] == 2
    assert [dict(row) for row in rows] == [
        {"account_id": "Z29587187", "source": "fidelity", "asset_name": "IBIT", "value": pytest.approx(12186.41)},
        {"account_id": "Z29587187", "source": "fidelity", "asset_name": "SPAXX**", "value": pytest.approx(19324.50)},
    ]


def test_run_snapshot_classifies_fidelity_cash_equivalents_without_seeded_classification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv_text = """Account Number,Account Name,Symbol,Description,Quantity,Last Price,Current Value
Z29587187,Trust: Under Agreement,SPAXX**,HELD IN MONEY MARKET,,, $19324.50
"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(snapshot_runner, "load_classification_overrides", lambda: {})

    def fail_suggestion(*args: object, **kwargs: object) -> None:
        pytest.fail("cash equivalents should classify by rule before LLM suggestion")

    monkeypatch.setattr(snapshot_runner, "fetch_bucket_suggestion", fail_suggestion)
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("Z29587187", None, "fidelity", "Trust: Under Agreement", "investment", "household", 1, "taxable"),
    )
    conn.commit()

    snapshot_runner.run_snapshot(
        conn,
        _settings(tmp_path),
        snapshot_date="2026-05-16",
        fidelity_csv=_write_csv(tmp_path, csv_text),
    )

    holding = conn.execute(
        """
        SELECT asset_name, is_cash_equivalent, bucket
        FROM holdings_snapshot
        WHERE snapshot_date = ? AND asset_name = ?
        """,
        ("2026-05-16", "SPAXX**"),
    ).fetchone()
    classification = conn.execute(
        "SELECT bucket, source FROM classifications WHERE asset_name = ?",
        ("SPAXX**",),
    ).fetchone()
    summary = conn.execute(
        """
        SELECT bucket, tax_treatment, owner_tag, total_value
        FROM snapshot_summary
        WHERE snapshot_date = ? AND bucket = ?
        """,
        ("2026-05-16", "Cash"),
    ).fetchone()
    conn.close()

    assert dict(holding) == {"asset_name": "SPAXX**", "is_cash_equivalent": 1, "bucket": "Cash"}
    assert dict(classification) == {"bucket": "Cash", "source": "rule"}
    assert dict(summary) == {
        "bucket": "Cash",
        "tax_treatment": "taxable",
        "owner_tag": "household",
        "total_value": pytest.approx(19324.50),
    }


def test_run_snapshot_preserves_existing_snapshot_when_fidelity_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    conn.execute(
        """
        INSERT INTO accounts (account_id, item_id, source, name, type, owner_tag, included, tax_treatment)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("existing", None, "user_managed", "Existing Account", "manual", "household", 1, "taxable"),
    )
    conn.execute(
        """
        INSERT INTO holdings_snapshot (
            snapshot_date, account_id, source, asset_name, display_name, value, bucket
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        ("2026-05-16", "existing", "user_managed", "Existing Asset", "Existing Asset", 123.45, "Cash"),
    )
    conn.execute(
        """
        INSERT INTO snapshot_summary (snapshot_date, bucket, tax_treatment, owner_tag, total_value)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("2026-05-16", "Cash", "taxable", "household", 123.45),
    )
    conn.commit()

    with pytest.raises(FidelityCsvError, match="not set up"):
        run_snapshot(
            conn,
            _settings(tmp_path),
            snapshot_date="2026-05-16",
            fidelity_csv=_write_csv(tmp_path),
        )

    holding_count = conn.execute(
        "SELECT COUNT(*) FROM holdings_snapshot WHERE snapshot_date = ?",
        ("2026-05-16",),
    ).fetchone()[0]
    summary_count = conn.execute(
        "SELECT COUNT(*) FROM snapshot_summary WHERE snapshot_date = ?",
        ("2026-05-16",),
    ).fetchone()[0]
    conn.close()

    assert holding_count == 1
    assert summary_count == 1


def test_snapshot_cli_reports_fidelity_csv_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv_path = _write_csv(tmp_path)
    monkeypatch.setattr(cli.Settings, "from_env", lambda: _settings(tmp_path))

    class FakeConnection:
        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "get_connection", lambda db_path: FakeConnection())
    monkeypatch.setattr(cli, "init_db", lambda conn: None)

    def fail_snapshot(*args: object, **kwargs: object) -> dict[str, object]:
        raise FidelityCsvError("Fidelity accounts not set up: Z29587187")

    monkeypatch.setattr(cli, "run_snapshot", fail_snapshot)

    with pytest.raises(typer.BadParameter, match="Fidelity accounts not set up: Z29587187"):
        cli.snapshot(fidelity_csv=csv_path)

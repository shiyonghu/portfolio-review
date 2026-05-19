from portfolio.db.connection import get_connection, init_db
from portfolio.managed.service import (
    add_managed_asset,
    append_valuation,
    list_latest,
    materialize_managed_rows,
    resolve_valuation,
)


def test_valuation_as_of_date(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    add_managed_asset(
        conn,
        asset_name="Primary Home",
        asset_kind="real_estate",
        value=1_000_000,
        effective_date="2026-01-01",
    )
    append_valuation(
        conn,
        asset_name="Primary Home",
        value=1_100_000,
        effective_date="2026-06-01",
        source="manual",
    )

    assert resolve_valuation(conn, "Primary Home", "2026-03-01")["value"] == 1_000_000
    assert resolve_valuation(conn, "Primary Home", "2026-07-01")["value"] == 1_100_000


def test_materialize_managed_rows_uses_latest_prior_valuation(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    account_id = add_managed_asset(
        conn,
        asset_name="Fund X",
        asset_kind="private_equity",
        value=200_000,
        effective_date="2026-01-10",
        owner_tag="household",
        tax_treatment="tax-advantaged",
    )
    append_valuation(
        conn,
        asset_name="Fund X",
        value=260_000,
        effective_date="2026-04-15",
        source="manual",
    )

    rows = materialize_managed_rows(conn, "2026-03-01")
    assert len(rows) == 1
    row = rows[0]
    assert row["account_id"] == account_id
    assert row["source"] == "user_managed"
    assert row["asset_name"] == "Fund X"
    assert row["asset_kind"] == "private_equity"
    assert row["value"] == 200_000
    assert row["quantity"] is None


def test_list_latest_returns_active_assets(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)
    add_managed_asset(
        conn,
        asset_name="Rental Condo",
        asset_kind="real_estate",
        value=500_000,
        effective_date="2026-01-01",
    )
    append_valuation(
        conn,
        asset_name="Rental Condo",
        value=530_000,
        effective_date="2026-05-01",
        source="manual",
    )

    latest = list_latest(conn)
    assert len(latest) == 1
    assert latest[0]["asset_name"] == "Rental Condo"
    assert latest[0]["value"] == 530_000


def test_add_managed_asset_accepts_equity_asset_kind(tmp_path) -> None:
    conn = get_connection(tmp_path / "portfolio.db")
    init_db(conn)

    add_managed_asset(
        conn,
        asset_name="Angel Investment",
        asset_kind="equity",
        value=75_000,
        effective_date="2026-05-16",
    )

    latest = list_latest(conn)
    assert len(latest) == 1
    assert latest[0]["asset_name"] == "Angel Investment"
    assert latest[0]["asset_kind"] == "equity"

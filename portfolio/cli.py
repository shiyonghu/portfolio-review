import webbrowser
from datetime import date

import typer
import uvicorn

from portfolio.agent.ask import ask_portfolio_question
from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db
from portfolio.db.queries import list_accounts, update_account
from portfolio.managed.service import (
    add_managed_asset,
    append_valuation,
    list_latest,
)
from portfolio.snapshot.console import print_snapshot_summary
from portfolio.snapshot.runner import run_snapshot

app = typer.Typer(help="Portfolio review tool")
managed_app = typer.Typer(help="Manage user-managed assets")

@app.callback()
def main():
    pass


@app.command()
def setup() -> None:
    """Link brokerage/bank accounts via Plaid."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    url = "http://localhost:8765"
    typer.echo(f"Starting Plaid Link setup server at {url}")
    webbrowser.open(url)
    uvicorn.run(
        "portfolio.plaid.link_server:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
    )


@app.command("accounts-list")
def accounts_list() -> None:
    """List linked accounts and preferences."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        rows = list_accounts(conn)
        if not rows:
            typer.echo("No accounts found. Run `portfolio setup` first.")
            return
        for row in rows:
            included = "yes" if row["included"] else "no"
            typer.echo(
                f"{row['account_id']}  {row['name']}  type={row['type']}  included={included}  "
                f"owner={row['owner_tag']}  tax={row['tax_treatment']}  ({row['subtype']})"
            )
    finally:
        conn.close()


@app.command("accounts-configure")
def accounts_configure(
    account_id: str = typer.Option(..., "--account-id", help="Plaid account id"),
    included: bool | None = typer.Option(None, "--included/--no-included"),
    owner_tag: str | None = typer.Option(None, "--owner-tag"),
    tax_treatment: str | None = typer.Option(
        None,
        "--tax-treatment",
        help="taxable or tax-advantaged",
    ),
) -> None:
    """Update account inclusion, owner tag, or tax treatment."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        update_account(
            conn,
            account_id,
            included=included,
            owner_tag=owner_tag,
            tax_treatment=tax_treatment,
        )
        typer.echo(f"Updated account {account_id}")
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        conn.close()


@managed_app.command("add")
def managed_add(
    asset_name: str = typer.Option(..., "--asset-name"),
    asset_kind: str = typer.Option(..., "--asset-kind"),
    value: float = typer.Option(..., "--value"),
    effective_date: str = typer.Option(date.today().isoformat(), "--effective-date"),
    owner_tag: str = typer.Option("household", "--owner-tag"),
    tax_treatment: str = typer.Option("taxable", "--tax-treatment"),
    source: str = typer.Option("manual", "--source"),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Add a user-managed asset and initial valuation."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        account_id = add_managed_asset(
            conn,
            asset_name=asset_name,
            asset_kind=asset_kind,
            value=value,
            effective_date=effective_date,
            owner_tag=owner_tag,
            tax_treatment=tax_treatment,
            source=source,
            notes=notes,
        )
        typer.echo(f"Added managed asset {asset_name} (account_id={account_id})")
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        conn.close()


@managed_app.command("update")
def managed_update(
    asset_name: str = typer.Argument(...),
    value: float = typer.Option(..., "--value"),
    effective_date: str = typer.Option(date.today().isoformat(), "--effective-date"),
    source: str = typer.Option("manual", "--source"),
    notes: str | None = typer.Option(None, "--notes"),
) -> None:
    """Append a valuation for an existing user-managed asset."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        append_valuation(
            conn,
            asset_name=asset_name,
            value=value,
            effective_date=effective_date,
            source=source,
            notes=notes,
        )
        typer.echo(f"Updated managed asset {asset_name}")
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    finally:
        conn.close()


@managed_app.command("list")
def managed_list() -> None:
    """List latest valuation for active user-managed assets."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        rows = list_latest(conn)
        if not rows:
            typer.echo("No managed assets found.")
            return
        for row in rows:
            typer.echo(
                f"{row['asset_name']}  kind={row['asset_kind']}  "
                f"value={row['value']}  as_of={row['effective_date']}"
            )
    finally:
        conn.close()


@app.command("snapshot")
def snapshot(
    snapshot_date: str | None = typer.Option(
        None,
        "--snapshot-date",
        help="ISO date; defaults to today",
    ),
) -> None:
    """Run full snapshot pipeline and export CSV."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        result = run_snapshot(conn, settings, snapshot_date=snapshot_date)
        print_snapshot_summary(conn, result["snapshot_date"])
    finally:
        conn.close()

    typer.echo(
        f"Snapshot complete: date={result['snapshot_date']} holdings={result['holdings_count']}"
    )
    typer.echo(f"Raw payloads: {result['raw_dir']}")
    typer.echo(f"CSV export: {result['csv_path']}")


@app.command("ask")
def ask(question: str = typer.Argument(..., help="Natural-language portfolio question")) -> None:
    """Ask the local Ollama-backed portfolio agent a question."""
    settings = Settings.from_env()
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
        answer = ask_portfolio_question(conn, settings, question)
    except RuntimeError as exc:
        raise typer.Exit(str(exc)) from exc
    finally:
        conn.close()

    typer.echo(answer)


app.add_typer(managed_app, name="managed")


if __name__ == "__main__":
    app()

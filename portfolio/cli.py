import webbrowser

import typer
import uvicorn

from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db
from portfolio.db.queries import list_accounts, update_account

app = typer.Typer(help="Portfolio review tool")

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
                f"{row['account_id']}  {row['name']}  included={included}  "
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


if __name__ == "__main__":
    app()

import webbrowser

import typer
import uvicorn

from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db

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

if __name__ == "__main__":
    app()

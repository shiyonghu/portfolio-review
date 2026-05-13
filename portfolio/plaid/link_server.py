"""FastAPI server used by `portfolio setup` to run Plaid Link locally."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

from portfolio.accounts.tax import derive_tax_treatment
from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db
from portfolio.keychain.tokens import save_access_token
from portfolio.plaid.client import make_plaid_client


def _ensure_db_initialized(settings: Settings) -> None:
    db_path = Path(settings.db_path)
    if db_path.exists():
        return
    conn = get_connection(db_path)
    try:
        init_db(conn)
    finally:
        conn.close()


class ExchangePublicTokenRequest(BaseModel):
    public_token: str


def create_app(settings: Settings, plaid_client: Any | None = None) -> FastAPI:
    _ensure_db_initialized(settings)
    app = FastAPI(title="Portfolio Plaid Link Server")
    app.state.settings = settings
    app.state.plaid_client = plaid_client or make_plaid_client(settings)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Portfolio Plaid Setup</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  </head>
  <body>
    <h1>Connect your account</h1>
    <button id="launch">Launch Plaid Link</button>
    <pre id="status"></pre>
    <script>
      const statusNode = document.getElementById("status");
      const button = document.getElementById("launch");

      async function getLinkToken() {
        const response = await fetch("/api/create_link_token", { method: "POST" });
        if (!response.ok) throw new Error("Failed to create link token");
        const data = await response.json();
        return data.link_token;
      }

      button.addEventListener("click", async () => {
        try {
          const linkToken = await getLinkToken();
          const handler = Plaid.create({
            token: linkToken,
            onSuccess: async (publicToken) => {
              const exchangeResponse = await fetch("/api/exchange_public_token", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ public_token: publicToken }),
              });
              const result = await exchangeResponse.json();
              statusNode.textContent = JSON.stringify(result, null, 2);
            },
            onExit: (error) => {
              if (error) statusNode.textContent = error.display_message || "Plaid Link exited";
            },
          });
          handler.open();
        } catch (error) {
          statusNode.textContent = String(error);
        }
      });
    </script>
  </body>
</html>
"""

    @app.post("/api/create_link_token")
    def create_link_token() -> dict[str, str]:
        plaid_request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=f"portfolio-{uuid4()}"),
            client_name="Portfolio Review",
            products=[Products("investments")],
            country_codes=[CountryCode("US")],
            language="en",
            # Register http://localhost:8765 as an allowed redirect URI in Plaid.
            redirect_uri="http://localhost:8765",
        )
        response = app.state.plaid_client.link_token_create(plaid_request)
        return {"link_token": response.link_token}

    @app.post("/api/exchange_public_token")
    def exchange_public_token(payload: ExchangePublicTokenRequest) -> dict[str, Any]:
        exchange_response = app.state.plaid_client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=payload.public_token)
        )
        item_id = exchange_response.item_id
        access_token = exchange_response.access_token
        save_access_token(item_id, access_token)

        accounts_response = app.state.plaid_client.accounts_get(
            AccountsGetRequest(access_token=access_token)
        )
        now = datetime.now(tz=timezone.utc).isoformat()

        conn = get_connection(app.state.settings.db_path)
        try:
            conn.execute(
                """
                INSERT INTO items (item_id, institution_name, status, last_synced_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    status = excluded.status,
                    last_synced_at = excluded.last_synced_at
                """,
                (item_id, None, "ok", now),
            )
            for account in accounts_response.accounts:
                conn.execute(
                    """
                    INSERT INTO accounts (
                        account_id, item_id, source, name, subtype, owner_tag, included, tax_treatment
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id) DO UPDATE SET
                        item_id = excluded.item_id,
                        source = excluded.source,
                        name = excluded.name,
                        subtype = excluded.subtype
                    """,
                    (
                        account.account_id,
                        item_id,
                        "plaid",
                        account.name,
                        account.subtype,
                        "household",
                        1,
                        derive_tax_treatment(
                            account.subtype.value
                            if hasattr(account.subtype, "value")
                            else str(account.subtype)
                        ),
                    ),
                )
            conn.commit()
        except Exception as exc:  # pragma: no cover - defensive rollback branch
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            conn.close()

        return {"item_id": item_id, "account_count": len(accounts_response.accounts)}

    return app


app = create_app(Settings.from_env())

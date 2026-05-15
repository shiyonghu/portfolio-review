"""FastAPI server used by `portfolio setup` to run Plaid Link locally."""

from __future__ import annotations

from datetime import datetime, timezone
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

from portfolio.config import Settings
from portfolio.db.connection import get_connection, init_db
from portfolio.keychain.tokens import load_access_token, save_access_token
from portfolio.plaid.accounts import serialize_plaid_accounts, upsert_plaid_accounts
from portfolio.plaid.client import make_plaid_client


def _ensure_db_initialized(settings: Settings) -> None:
    conn = get_connection(settings.db_path)
    try:
        init_db(conn)
    finally:
        conn.close()


class ExchangePublicTokenRequest(BaseModel):
    public_token: str


class ConfirmAccountsRequest(BaseModel):
    item_id: str
    included_account_ids: list[str]


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
    <section id="account-selection" hidden>
      <h2>Select accounts to track</h2>
      <p>Choose which accounts from this institution should be included in portfolio snapshots.</p>
      <form id="account-form"></form>
      <button type="submit" form="account-form" id="confirm-accounts">Save selection</button>
    </section>
    <pre id="status"></pre>
    <script>
      const statusNode = document.getElementById("status");
      const button = document.getElementById("launch");
      const selectionSection = document.getElementById("account-selection");
      const accountForm = document.getElementById("account-form");
      let pendingItemId = null;

      function showAccountSelection(itemId, accounts) {
        pendingItemId = itemId;
        accountForm.innerHTML = "";
        for (const account of accounts) {
          const label = document.createElement("label");
          label.style.display = "block";
          label.style.marginBottom = "0.5rem";

          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.name = "account_id";
          checkbox.value = account.account_id;
          checkbox.checked = true;

          const subtype = account.subtype ? ` (${account.subtype})` : "";
          label.append(checkbox, ` ${account.name}${subtype}`);
          accountForm.append(label);
        }
        selectionSection.hidden = false;
        statusNode.textContent = `Linked item ${itemId}. Select accounts to track.`;
      }

      async function getLinkToken() {
        const response = await fetch("/api/create_link_token", { method: "POST" });
        if (!response.ok) throw new Error("Failed to create link token");
        const data = await response.json();
        return data.link_token;
      }

      button.addEventListener("click", async () => {
        try {
          selectionSection.hidden = true;
          pendingItemId = null;
          const linkToken = await getLinkToken();
          const handler = Plaid.create({
            token: linkToken,
            onSuccess: async (publicToken) => {
              const exchangeResponse = await fetch("/api/exchange_public_token", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ public_token: publicToken }),
              });
              if (!exchangeResponse.ok) {
                const error = await exchangeResponse.json();
                statusNode.textContent = error.detail || "Failed to exchange public token";
                return;
              }
              const result = await exchangeResponse.json();
              showAccountSelection(result.item_id, result.accounts);
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

      accountForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!pendingItemId) return;

        const includedAccountIds = Array.from(
          accountForm.querySelectorAll('input[name="account_id"]:checked'),
        ).map((input) => input.value);

        try {
          const response = await fetch("/api/confirm_accounts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              item_id: pendingItemId,
              included_account_ids: includedAccountIds,
            }),
          });
          const result = await response.json();
          if (!response.ok) {
            statusNode.textContent = result.detail || "Failed to save account selection";
            return;
          }
          statusNode.textContent = JSON.stringify(result, null, 2);
          selectionSection.hidden = true;
          pendingItemId = null;
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
        link_kwargs: dict[str, Any] = {
            "user": LinkTokenCreateRequestUser(client_user_id=f"portfolio-{uuid4()}"),
            "client_name": "Portfolio Review",
            "products": [Products("investments")],
            "country_codes": [CountryCode("US")],
            "language": "en",
        }
        if app.state.settings.plaid_env == "sandbox":
            # Sandbox only: http localhost allowed by Plaid. Register in Dashboard allowlist.
            link_kwargs["redirect_uri"] = "http://localhost:8765"
        plaid_request = LinkTokenCreateRequest(**link_kwargs)
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
            conn.commit()
        except Exception as exc:  # pragma: no cover - defensive rollback branch
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            conn.close()

        return {
            "item_id": item_id,
            "accounts": serialize_plaid_accounts(accounts_response.accounts),
        }

    @app.post("/api/confirm_accounts")
    def confirm_accounts(payload: ConfirmAccountsRequest) -> dict[str, Any]:
        access_token = load_access_token(payload.item_id)
        if not access_token:
            raise HTTPException(status_code=404, detail=f"No access token for item {payload.item_id}")

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
                (payload.item_id, None, "ok", now),
            )
            account_count = upsert_plaid_accounts(
                conn,
                payload.item_id,
                accounts_response.accounts,
                payload.included_account_ids,
            )
        except Exception as exc:  # pragma: no cover - defensive rollback branch
            conn.rollback()
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            conn.close()

        included_count = len(payload.included_account_ids)
        return {
            "item_id": payload.item_id,
            "account_count": account_count,
            "included_count": included_count,
        }

    return app


app = create_app(Settings.from_env())

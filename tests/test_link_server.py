from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from plaid.model.account_subtype import AccountSubtype
from plaid.model.country_code import CountryCode
from plaid.model.products import Products

from portfolio.config import Settings
from portfolio.db.connection import get_connection
from portfolio.plaid.link_server import create_app


def _settings(tmp_path) -> Settings:
    return Settings(
        plaid_client_id="test-client-id",
        plaid_secret="test-secret",
        plaid_env="sandbox",
        db_path=str(tmp_path / "portfolio.db"),
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.1",
    )


def _account(account_id: str, name: str, subtype: str) -> MagicMock:
    account = MagicMock()
    account.account_id = account_id
    account.name = name
    account.subtype = AccountSubtype(subtype)
    account.type = "investment"
    return account


def test_create_app_builds_fastapi_app(tmp_path) -> None:
    app = create_app(_settings(tmp_path), plaid_client=MagicMock())
    assert app is not None


def test_create_link_token_returns_token(tmp_path) -> None:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.link_token = "link-sandbox-123"
    mock_client.link_token_create.return_value = mock_response
    app = create_app(_settings(tmp_path), plaid_client=mock_client)

    with TestClient(app) as client:
        response = client.post("/api/create_link_token")

    assert response.status_code == 200
    assert response.json() == {"link_token": "link-sandbox-123"}

    mock_client.link_token_create.assert_called_once()
    request = mock_client.link_token_create.call_args[0][0]
    assert Products("investments") in request.products
    assert CountryCode("US") in request.country_codes


@patch("portfolio.plaid.link_server.save_access_token")
def test_exchange_public_token_returns_accounts_without_persisting_them(
    mock_save_token, tmp_path
) -> None:
    mock_client = MagicMock()
    exchange_response = MagicMock()
    exchange_response.item_id = "item-123"
    exchange_response.access_token = "access-token"
    mock_client.item_public_token_exchange.return_value = exchange_response

    account = _account("acct-1", "Brokerage", "brokerage")
    accounts_response = MagicMock()
    accounts_response.accounts = [account]
    mock_client.accounts_get.return_value = accounts_response

    app = create_app(_settings(tmp_path), plaid_client=mock_client)
    with TestClient(app) as client:
        response = client.post(
            "/api/exchange_public_token",
            json={"public_token": "public-token"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "item_id": "item-123",
        "accounts": [
            {
                "account_id": "acct-1",
                "name": "Brokerage",
                "subtype": "brokerage",
                "type": "investment",
            }
        ],
    }
    mock_save_token.assert_called_once_with("item-123", "access-token")

    conn = get_connection(tmp_path / "portfolio.db")
    row = conn.execute("SELECT COUNT(*) AS count FROM accounts").fetchone()
    conn.close()
    assert row is not None
    assert row["count"] == 0


@patch("portfolio.plaid.link_server.load_access_token", return_value="access-token")
def test_confirm_accounts_persists_included_selection(mock_load_token, tmp_path) -> None:
    mock_client = MagicMock()
    accounts_response = MagicMock()
    accounts_response.accounts = [
        _account("acct-1", "Brokerage", "brokerage"),
        _account("acct-2", "401k", "401k"),
    ]
    mock_client.accounts_get.return_value = accounts_response

    app = create_app(_settings(tmp_path), plaid_client=mock_client)
    with TestClient(app) as client:
        response = client.post(
            "/api/confirm_accounts",
            json={"item_id": "item-123", "included_account_ids": ["acct-2"]},
        )

    assert response.status_code == 200
    assert response.json() == {
        "item_id": "item-123",
        "account_count": 2,
        "included_count": 1,
    }

    conn = get_connection(tmp_path / "portfolio.db")
    rows = conn.execute(
        "SELECT account_id, included, tax_treatment FROM accounts ORDER BY account_id"
    ).fetchall()
    conn.close()
    assert [dict(row) for row in rows] == [
        {"account_id": "acct-1", "included": 0, "tax_treatment": "taxable"},
        {"account_id": "acct-2", "included": 1, "tax_treatment": "tax-advantaged"},
    ]

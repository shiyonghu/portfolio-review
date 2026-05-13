from __future__ import annotations

from unittest.mock import MagicMock, patch

from plaid.configuration import Environment

from portfolio.config import Settings
from portfolio.plaid.client import (
    exchange_public_token,
    fetch_balances,
    fetch_holdings,
    make_plaid_client,
)


def _settings(**overrides) -> Settings:
    base = dict(
        plaid_client_id="test_client_id",
        plaid_secret="test_secret",
        plaid_env="sandbox",
        db_path="portfolio.db",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.1",
    )
    base.update(overrides)
    return Settings(**base)


@patch("portfolio.plaid.client.PlaidApi")
@patch("portfolio.plaid.client.ApiClient")
@patch("portfolio.plaid.client.Configuration")
def test_make_plaid_client_uses_sandbox_host(
    mock_configuration: MagicMock,
    mock_api_client: MagicMock,
    mock_plaid_api: MagicMock,
) -> None:
    settings = _settings(plaid_env="sandbox")
    make_plaid_client(settings)

    mock_configuration.assert_called_once_with(
        host=Environment.Sandbox,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    mock_api_client.assert_called_once_with(mock_configuration.return_value)
    mock_plaid_api.assert_called_once_with(mock_api_client.return_value)


@patch("portfolio.plaid.client.PlaidApi")
@patch("portfolio.plaid.client.ApiClient")
@patch("portfolio.plaid.client.Configuration")
def test_make_plaid_client_uses_production_host(
    mock_configuration: MagicMock,
    mock_api_client: MagicMock,
    mock_plaid_api: MagicMock,
) -> None:
    settings = _settings(plaid_env="production")
    make_plaid_client(settings)

    mock_configuration.assert_called_once_with(
        host=Environment.Production,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )


def test_exchange_public_token_calls_item_public_token_exchange() -> None:
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.access_token = "access-token-xyz"
    client.item_public_token_exchange.return_value = mock_response

    assert exchange_public_token(client, "public-tok") == "access-token-xyz"

    client.item_public_token_exchange.assert_called_once()
    req = client.item_public_token_exchange.call_args[0][0]
    assert req.public_token == "public-tok"


def test_fetch_balances_calls_accounts_balance_get() -> None:
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.to_dict.return_value = {"accounts": [], "request_id": "r1"}
    client.accounts_balance_get.return_value = mock_response

    assert fetch_balances(client, "access-tok") == {
        "accounts": [],
        "request_id": "r1",
    }

    client.accounts_balance_get.assert_called_once()
    req = client.accounts_balance_get.call_args[0][0]
    assert req.access_token == "access-tok"


def test_fetch_holdings_calls_investments_holdings_get() -> None:
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.to_dict.return_value = {"accounts": [], "holdings": []}
    client.investments_holdings_get.return_value = mock_response

    assert fetch_holdings(client, "access-tok") == {
        "accounts": [],
        "holdings": [],
    }

    client.investments_holdings_get.assert_called_once()
    req = client.investments_holdings_get.call_args[0][0]
    assert req.access_token == "access-tok"

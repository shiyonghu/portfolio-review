"""Thin wrapper around the Plaid Python SDK."""

from __future__ import annotations

from plaid import ApiClient, Configuration, Environment
from plaid.api.plaid_api import PlaidApi
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

from portfolio.config import Settings


def make_plaid_client(settings: Settings) -> PlaidApi:
    host = (
        Environment.Sandbox
        if settings.plaid_env == "sandbox"
        else Environment.Production
    )
    configuration = Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return PlaidApi(ApiClient(configuration))


def exchange_public_token(client: PlaidApi, public_token: str) -> str:
    request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(request)
    return response.access_token


def fetch_balances(client: PlaidApi, access_token: str) -> dict:
    request = AccountsBalanceGetRequest(access_token=access_token)
    response = client.accounts_balance_get(request)
    return response.to_dict()


def fetch_holdings(client: PlaidApi, access_token: str) -> dict:
    request = InvestmentsHoldingsGetRequest(access_token=access_token)
    response = client.investments_holdings_get(request)
    return response.to_dict()

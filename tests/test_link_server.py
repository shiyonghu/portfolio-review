from __future__ import annotations

from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from plaid.model.country_code import CountryCode
from plaid.model.products import Products

from portfolio.config import Settings
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

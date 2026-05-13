from portfolio.config import Settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("PLAID_CLIENT_ID", "cid")
    monkeypatch.setenv("PLAID_SECRET", "sec")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    s = Settings.from_env()
    assert s.plaid_client_id == "cid"
    assert s.plaid_env == "sandbox"

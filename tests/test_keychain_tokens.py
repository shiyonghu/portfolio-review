from unittest.mock import patch

from portfolio.keychain.tokens import delete_access_token, load_access_token, save_access_token


@patch("keyring.set_password")
def test_save_access_token(mock_set):
    save_access_token("item_abc", "access_xyz")
    mock_set.assert_called_once_with("portfolio-review", "item_abc", "access_xyz")


@patch("keyring.get_password", return_value="access_xyz")
def test_load_access_token(mock_get):
    assert load_access_token("item_abc") == "access_xyz"
    mock_get.assert_called_once_with("portfolio-review", "item_abc")


@patch("keyring.delete_password")
def test_delete_access_token(mock_delete):
    delete_access_token("item_abc")
    mock_delete.assert_called_once_with("portfolio-review", "item_abc")

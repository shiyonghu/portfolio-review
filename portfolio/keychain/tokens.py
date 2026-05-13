import keyring

SERVICE_NAME = "portfolio-review"


def save_access_token(item_id: str, token: str) -> None:
    keyring.set_password(SERVICE_NAME, item_id, token)


def load_access_token(item_id: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, item_id)


def delete_access_token(item_id: str) -> None:
    keyring.delete_password(SERVICE_NAME, item_id)

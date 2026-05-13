import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_connection(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def db_is_initialized(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='items' LIMIT 1"
    ).fetchone()
    return row is not None


def init_db(conn: sqlite3.Connection) -> None:
    if db_is_initialized(conn):
        return
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()

-- Portfolio SQLite schema (v1). Enable foreign keys via PRAGMA in application code.

CREATE TABLE items (
    item_id TEXT PRIMARY KEY NOT NULL,
    institution_name TEXT,
    status TEXT,
    last_synced_at TEXT
);

CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY NOT NULL,
    item_id TEXT REFERENCES items (item_id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('plaid', 'user_managed')),
    name TEXT,
    subtype TEXT,
    owner_tag TEXT,
    included INTEGER NOT NULL DEFAULT 1,
    tax_treatment TEXT NOT NULL CHECK (tax_treatment IN ('taxable', 'tax-advantaged')),
    tax_treatment_override TEXT CHECK (
        tax_treatment_override IS NULL
        OR tax_treatment_override IN ('taxable', 'tax-advantaged')
    )
);

CREATE TABLE user_managed_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_name TEXT NOT NULL,
    asset_kind TEXT NOT NULL CHECK (
        asset_kind IN ('real_estate', 'private_equity', 'other')
    ),
    account_id TEXT NOT NULL REFERENCES accounts (account_id) ON DELETE CASCADE,
    value REAL NOT NULL,
    effective_date TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'llm')),
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime ('now')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE holdings_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts (account_id) ON DELETE CASCADE,
    source TEXT NOT NULL CHECK (source IN ('plaid', 'user_managed')),
    asset_name TEXT NOT NULL,
    display_name TEXT,
    plaid_security_id TEXT,
    plaid_type TEXT,
    plaid_subtype TEXT,
    is_cash_equivalent INTEGER CHECK (is_cash_equivalent IN (0, 1)),
    quantity REAL,
    unit_price REAL,
    price_as_of TEXT,
    value REAL NOT NULL,
    bucket TEXT,
    UNIQUE (snapshot_date, account_id, asset_name, source)
);

CREATE TABLE classifications (
    asset_name TEXT PRIMARY KEY NOT NULL,
    bucket TEXT NOT NULL,
    source TEXT NOT NULL CHECK (
        source IN ('yaml', 'rule', 'asset_kind_default', 'llm_confirmed')
    ),
    classified_at TEXT NOT NULL
);

CREATE TABLE snapshot_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    bucket TEXT NOT NULL,
    tax_treatment TEXT NOT NULL CHECK (tax_treatment IN ('taxable', 'tax-advantaged')),
    owner_tag TEXT NOT NULL,
    total_value REAL NOT NULL,
    UNIQUE (snapshot_date, bucket, tax_treatment, owner_tag)
);

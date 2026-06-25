from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS prices (
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    adjusted_close REAL,
    volume REAL,
    fetched_at TEXT NOT NULL,
    source_payload_hash TEXT,
    PRIMARY KEY (provider, provider_symbol, date)
);

CREATE INDEX IF NOT EXISTS idx_prices_symbol_date
    ON prices (symbol, date);

CREATE TABLE IF NOT EXISTS egarch_results (
    symbol TEXT NOT NULL,
    provider TEXT NOT NULL,
    window INTEGER NOT NULL,
    as_of_date TEXT NOT NULL,
    model_spec_hash TEXT NOT NULL,
    return_type TEXT NOT NULL,
    distribution TEXT NOT NULL,
    variance_daily REAL NOT NULL,
    volatility_daily REAL NOT NULL,
    volatility_annualized REAL NOT NULL,
    parameters_json TEXT NOT NULL,
    diagnostics_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (symbol, window, as_of_date, model_spec_hash)
);

CREATE TABLE IF NOT EXISTS refresh_runs (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'partial')),
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    rows_upserted INTEGER NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT
);
"""


def connect_database(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.commit()

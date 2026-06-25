from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from egarch_service.domain import DailyBar

SCHEMA = """
create table if not exists prices (
 provider text not null, symbol text not null, provider_symbol text not null, date text not null,
 open real, high real, low real, close real not null, adjusted_close real, volume real,
 fetched_at text not null, source_payload_hash text, primary key(provider, provider_symbol, date));
create table if not exists egarch_results (
 symbol text not null, provider text not null, window integer not null, as_of_date text not null,
 model_spec_hash text not null, return_type text not null, distribution text not null,
 variance_daily real not null, volatility_daily real not null, volatility_annualized real not null,
 parameters_json text not null, diagnostics_json text not null, warnings_json text not null, response_json text not null,
 created_at text not null, primary key(symbol, window, as_of_date, model_spec_hash));
create table if not exists refresh_runs (
 id text primary key, provider text not null, symbol text not null, started_at text not null, finished_at text,
 status text not null, requested_start text not null, requested_end text not null, rows_upserted integer not null default 0,
 error_code text, error_message text);
"""

class SQLiteStorage:
    def __init__(self, path: str | Path = "egarch.db") -> None:
        self.path = str(path)
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_prices(self, bars: list[DailyBar]) -> int:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.executemany(
                """insert into prices(provider,symbol,provider_symbol,date,open,high,low,close,adjusted_close,volume,fetched_at,source_payload_hash)
                values(?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(provider, provider_symbol, date) do update set symbol=excluded.symbol, open=excluded.open, high=excluded.high,
                low=excluded.low, close=excluded.close, adjusted_close=excluded.adjusted_close, volume=excluded.volume,
                fetched_at=excluded.fetched_at, source_payload_hash=excluded.source_payload_hash""",
                [(b.provider,b.symbol,b.provider_symbol,b.date.isoformat(),b.open,b.high,b.low,b.close,b.adjusted_close,b.volume,(b.fetched_at.isoformat() if b.fetched_at else now),b.source_payload_hash) for b in bars],
            )
        return len(bars)

    def get_prices(self, provider: str, provider_symbol: str, end_date: date, limit: int) -> list[DailyBar]:
        with self.connect() as conn:
            rows = conn.execute(
                "select * from prices where provider=? and provider_symbol=? and date<=? order by date desc limit ?",
                (provider, provider_symbol, end_date.isoformat(), limit),
            ).fetchall()
        return [_bar(r) for r in reversed(rows)]

    def latest_price_date(self, provider: str, provider_symbol: str) -> date | None:
        with self.connect() as conn:
            row = conn.execute("select max(date) as d from prices where provider=? and provider_symbol=?", (provider, provider_symbol)).fetchone()
        return date.fromisoformat(row["d"]) if row and row["d"] else None

    def start_refresh(self, provider: str, symbol: str, start: date, end: date) -> str:
        run_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute("insert into refresh_runs(id,provider,symbol,started_at,status,requested_start,requested_end,rows_upserted) values(?,?,?,?,?,?,?,0)", (run_id, provider, symbol, datetime.now(UTC).isoformat(), "partial", start.isoformat(), end.isoformat()))
        return run_id

    def finish_refresh(self, run_id: str, status: str, rows: int, error_code: str | None = None, error_message: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute("update refresh_runs set finished_at=?, status=?, rows_upserted=?, error_code=?, error_message=? where id=?", (datetime.now(UTC).isoformat(), status, rows, error_code, error_message, run_id))

    def get_result(self, symbol: str, window: int, as_of: date, spec_hash: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("select response_json from egarch_results where symbol=? and window=? and as_of_date=? and model_spec_hash=?", (symbol, window, as_of.isoformat(), spec_hash)).fetchone()
        return json.loads(row["response_json"]) if row else None

    def upsert_result(self, response: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute("""insert into egarch_results values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(symbol, window, as_of_date, model_spec_hash) do update set variance_daily=excluded.variance_daily,
            volatility_daily=excluded.volatility_daily, volatility_annualized=excluded.volatility_annualized, parameters_json=excluded.parameters_json,
            diagnostics_json=excluded.diagnostics_json, warnings_json=excluded.warnings_json, response_json=excluded.response_json, created_at=excluded.created_at""",
            (response["symbol"], response["provider"], response["window"], response["as_of_date"], response["model"]["model_spec_hash"], response["model"]["return_type"], response["model"]["distribution"], response["forecast"]["variance_daily"], response["forecast"]["volatility_daily"], response["forecast"]["volatility_annualized"], json.dumps(response["parameters"], sort_keys=True), json.dumps(response["diagnostics"], sort_keys=True), json.dumps(response["warnings"]), json.dumps(response, sort_keys=True), datetime.now(UTC).isoformat()))

def _bar(row: sqlite3.Row) -> DailyBar:
    return DailyBar(row["provider"], row["symbol"], row["provider_symbol"], date.fromisoformat(row["date"]), row["open"], row["high"], row["low"], row["close"], row["adjusted_close"], row["volume"], datetime.fromisoformat(row["fetched_at"]), row["source_payload_hash"])

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from egarch_service.data.providers import DailyBar


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalized_payload_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


class CacheFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class RefreshRun:
    id: str
    provider: str
    symbol: str
    started_at: str
    finished_at: str | None
    status: str
    requested_start: date
    requested_end: date
    rows_upserted: int
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class EgarchResultRecord:
    symbol: str
    provider: str
    window: int
    as_of_date: date
    model_spec_hash: str
    return_type: str
    distribution: str
    variance_daily: float
    volatility_daily: float
    volatility_annualized: float
    parameters: dict[str, Any]
    diagnostics: dict[str, Any]
    warnings: list[str]
    created_at: str | None = None


def _date_to_text(value: date) -> str:
    return value.isoformat()


def _date_from_text(value: str) -> date:
    return date.fromisoformat(value)


class PriceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_daily_bars(self, bars: list[DailyBar], fetched_at: str | None = None) -> int:
        if not bars:
            return 0
        timestamp = fetched_at or utc_now_iso()
        rows = [
            (
                bar.provider,
                bar.symbol,
                bar.provider_symbol,
                _date_to_text(bar.date),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.adjusted_close,
                bar.volume,
                timestamp,
                bar.source_payload_hash,
            )
            for bar in bars
        ]
        with self._connection:
            cursor = self._connection.executemany(
                """
                INSERT INTO prices (
                    provider, symbol, provider_symbol, date, open, high, low, close,
                    adjusted_close, volume, fetched_at, source_payload_hash
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_symbol, date) DO UPDATE SET
                    symbol = excluded.symbol,
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adjusted_close = excluded.adjusted_close,
                    volume = excluded.volume,
                    fetched_at = excluded.fetched_at,
                    source_payload_hash = excluded.source_payload_hash
                """,
                rows,
            )
        return cursor.rowcount

    def latest_price_date(self, provider: str, provider_symbol: str) -> date | None:
        row = self._connection.execute(
            """
            SELECT MAX(date) AS latest_date
            FROM prices
            WHERE provider = ? AND provider_symbol = ?
            """,
            (provider, provider_symbol),
        ).fetchone()
        if row is None or row["latest_date"] is None:
            return None
        return _date_from_text(str(row["latest_date"]))

    def has_price_through(self, provider: str, provider_symbol: str, expected_as_of_date: date) -> bool:
        latest = self.latest_price_date(provider, provider_symbol)
        return latest is not None and latest >= expected_as_of_date

    def cache_freshness(
        self,
        provider: str,
        provider_symbol: str,
        expected_as_of_date: date,
    ) -> CacheFreshness:
        latest = self.latest_price_date(provider, provider_symbol)
        if latest is None:
            return CacheFreshness.EMPTY
        if latest >= expected_as_of_date:
            return CacheFreshness.FRESH
        return CacheFreshness.STALE

    def get_daily_bars(
        self,
        provider: str,
        provider_symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyBar]:
        clauses = ["provider = ?", "provider_symbol = ?"]
        params: list[object] = [provider, provider_symbol]
        if start_date is not None:
            clauses.append("date >= ?")
            params.append(_date_to_text(start_date))
        if end_date is not None:
            clauses.append("date <= ?")
            params.append(_date_to_text(end_date))
        rows = self._connection.execute(
            f"""
            SELECT provider, symbol, provider_symbol, date, open, high, low, close,
                   adjusted_close, volume, source_payload_hash
            FROM prices
            WHERE {' AND '.join(clauses)}
            ORDER BY date ASC
            """,
            params,
        ).fetchall()
        return [
            DailyBar(
                provider=str(row["provider"]),
                symbol=str(row["symbol"]),
                provider_symbol=str(row["provider_symbol"]),
                date=_date_from_text(str(row["date"])),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=float(row["close"]),
                adjusted_close=row["adjusted_close"],
                volume=row["volume"],
                source_payload_hash=row["source_payload_hash"],
            )
            for row in rows
        ]


class EgarchResultRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_result(self, result: EgarchResultRecord) -> None:
        created_at = result.created_at or utc_now_iso()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO egarch_results (
                    symbol, provider, window, as_of_date, model_spec_hash, return_type,
                    distribution, variance_daily, volatility_daily, volatility_annualized,
                    parameters_json, diagnostics_json, warnings_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, window, as_of_date, model_spec_hash) DO UPDATE SET
                    provider = excluded.provider,
                    return_type = excluded.return_type,
                    distribution = excluded.distribution,
                    variance_daily = excluded.variance_daily,
                    volatility_daily = excluded.volatility_daily,
                    volatility_annualized = excluded.volatility_annualized,
                    parameters_json = excluded.parameters_json,
                    diagnostics_json = excluded.diagnostics_json,
                    warnings_json = excluded.warnings_json,
                    created_at = excluded.created_at
                """,
                (
                    result.symbol,
                    result.provider,
                    result.window,
                    _date_to_text(result.as_of_date),
                    result.model_spec_hash,
                    result.return_type,
                    result.distribution,
                    result.variance_daily,
                    result.volatility_daily,
                    result.volatility_annualized,
                    json.dumps(result.parameters, sort_keys=True),
                    json.dumps(result.diagnostics, sort_keys=True),
                    json.dumps(result.warnings),
                    created_at,
                ),
            )

    def get_result(
        self,
        symbol: str,
        window: int,
        as_of_date: date,
        model_spec_hash: str,
    ) -> EgarchResultRecord | None:
        row = self._connection.execute(
            """
            SELECT * FROM egarch_results
            WHERE symbol = ? AND window = ? AND as_of_date = ? AND model_spec_hash = ?
            """,
            (symbol, window, _date_to_text(as_of_date), model_spec_hash),
        ).fetchone()
        if row is None:
            return None
        return EgarchResultRecord(
            symbol=str(row["symbol"]),
            provider=str(row["provider"]),
            window=int(row["window"]),
            as_of_date=_date_from_text(str(row["as_of_date"])),
            model_spec_hash=str(row["model_spec_hash"]),
            return_type=str(row["return_type"]),
            distribution=str(row["distribution"]),
            variance_daily=float(row["variance_daily"]),
            volatility_daily=float(row["volatility_daily"]),
            volatility_annualized=float(row["volatility_annualized"]),
            parameters=json.loads(str(row["parameters_json"])),
            diagnostics=json.loads(str(row["diagnostics_json"])),
            warnings=json.loads(str(row["warnings_json"])),
            created_at=str(row["created_at"]),
        )


class RefreshRunRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def start_run(
        self,
        provider: str,
        symbol: str,
        requested_start: date,
        requested_end: date,
    ) -> RefreshRun:
        run = RefreshRun(
            id=str(uuid.uuid4()),
            provider=provider,
            symbol=symbol,
            started_at=utc_now_iso(),
            finished_at=None,
            status="running",
            requested_start=requested_start,
            requested_end=requested_end,
            rows_upserted=0,
            error_code=None,
            error_message=None,
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO refresh_runs (
                    id, provider, symbol, started_at, finished_at, status,
                    requested_start, requested_end, rows_upserted, error_code, error_message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.id,
                    run.provider,
                    run.symbol,
                    run.started_at,
                    run.finished_at,
                    run.status,
                    _date_to_text(run.requested_start),
                    _date_to_text(run.requested_end),
                    run.rows_upserted,
                    run.error_code,
                    run.error_message,
                ),
            )
        return run

    def finish_run(
        self,
        run_id: str,
        status: str,
        rows_upserted: int,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> RefreshRun:
        if status not in {"success", "failed", "partial"}:
            raise ValueError("finished refresh run status must be success, failed, or partial")
        finished_at = utc_now_iso()
        sanitized_error_message = error_message[:500] if error_message is not None else None
        with self._connection:
            self._connection.execute(
                """
                UPDATE refresh_runs
                SET finished_at = ?, status = ?, rows_upserted = ?, error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (finished_at, status, rows_upserted, error_code, sanitized_error_message, run_id),
            )
        run = self.get_run(run_id)
        if run is None:
            raise ValueError(f"refresh run not found: {run_id}")
        return run

    def get_run(self, run_id: str) -> RefreshRun | None:
        row = self._connection.execute(
            "SELECT * FROM refresh_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return RefreshRun(
            id=str(row["id"]),
            provider=str(row["provider"]),
            symbol=str(row["symbol"]),
            started_at=str(row["started_at"]),
            finished_at=row["finished_at"],
            status=str(row["status"]),
            requested_start=_date_from_text(str(row["requested_start"])),
            requested_end=_date_from_text(str(row["requested_end"])),
            rows_upserted=int(row["rows_upserted"]),
            error_code=row["error_code"],
            error_message=row["error_message"],
        )

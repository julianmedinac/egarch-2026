from __future__ import annotations

import math
import random
import time
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from egarch_service.assets.registry import Asset
from egarch_service.data.providers import DailyBar
from egarch_service.data.repositories import normalized_payload_hash


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class YahooMarketDataProvider:
    provider_name = "yahoo"

    def __init__(self, timeout_seconds: float = 10.0, max_retries: int = 3) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def fetch_daily_bars(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._fetch_once(asset, start_date, end_date)
            except Exception as exc:  # noqa: BLE001 - provider boundary normalizes third-party errors
                last_error = exc
                if attempt == self.max_retries:
                    break
                delay = min(2.0, 0.25 * (2 ** (attempt - 1))) + random.uniform(0, 0.1)
                time.sleep(delay)
        message = str(last_error) if last_error is not None else "unknown Yahoo provider failure"
        raise ProviderError("provider_unavailable", message) from last_error

    def _fetch_once(self, asset: Asset, start_date: date, end_date: date) -> list[DailyBar]:
        frame = yf.download(
            tickers=asset.provider_symbol,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            progress=False,
            timeout=self.timeout_seconds,
            threads=False,
        )
        if not isinstance(frame, pd.DataFrame):
            raise ProviderError("provider_unavailable", "Yahoo response was not tabular")
        if frame.empty:
            return []
        normalized = _flatten_yahoo_frame(frame)
        bars: list[DailyBar] = []
        for index, row in normalized.iterrows():
            bar_date = pd.Timestamp(index).date()
            if bar_date < start_date or bar_date > end_date:
                continue
            close = _optional_float(row.get("Close"))
            if close is None:
                continue
            payload = {
                "provider": self.provider_name,
                "symbol": asset.symbol,
                "provider_symbol": asset.provider_symbol,
                "date": bar_date.isoformat(),
                "open": _optional_float(row.get("Open")),
                "high": _optional_float(row.get("High")),
                "low": _optional_float(row.get("Low")),
                "close": close,
                "adjusted_close": _optional_float(row.get("Adj Close")),
                "volume": _optional_float(row.get("Volume")),
            }
            bars.append(
                DailyBar(
                    provider=self.provider_name,
                    symbol=asset.symbol,
                    provider_symbol=asset.provider_symbol,
                    date=bar_date,
                    open=payload["open"],
                    high=payload["high"],
                    low=payload["low"],
                    close=close,
                    adjusted_close=payload["adjusted_close"],
                    volume=payload["volume"],
                    source_payload_hash=normalized_payload_hash(payload),
                )
            )
        return bars


def _flatten_yahoo_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        if len(frame.columns.names) > 1 and "Price" in frame.columns.names:
            return frame.droplevel([name for name in frame.columns.names if name != "Price"], axis=1)
        return frame.droplevel(-1, axis=1)
    return frame


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


YahooFinanceProvider = YahooMarketDataProvider

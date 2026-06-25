from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from egarch_service.assets.registry import Asset


@dataclass(frozen=True, slots=True)
class DailyBar:
    provider: str
    symbol: str
    provider_symbol: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adjusted_close: float | None = None
    volume: float | None = None
    source_payload_hash: str | None = None


class MarketDataProvider(Protocol):
    provider_name: str

    def fetch_daily_bars(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]: ...

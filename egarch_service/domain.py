from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class AssetClass(StrEnum):
    EQUITY = "equity"
    FUTURE = "future"
    CRYPTO = "crypto"


class CalendarRule(StrEnum):
    US_EQUITY = "us_equity"
    FUTURES_PROVIDER = "futures_provider"
    CRYPTO_24_7 = "crypto_24_7"


class PriceField(StrEnum):
    CLOSE = "close"
    ADJUSTED_CLOSE = "adjusted_close"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"


class ServiceError(Exception):
    status_code = 500
    error_code = "internal_error"

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        if error_code is not None:
            self.error_code = error_code


class UnsupportedSymbolError(ServiceError):
    status_code = 400
    error_code = "unsupported_symbol"


class UnsupportedWindowError(ServiceError):
    status_code = 400
    error_code = "unsupported_window"


class StaleDataError(ServiceError):
    status_code = 409
    error_code = "stale_data"


class InsufficientHistoryError(ServiceError):
    status_code = 422
    error_code = "insufficient_history"


class ModelFailedError(ServiceError):
    status_code = 422
    error_code = "model_failed_to_converge"


class ProviderUnavailableError(ServiceError):
    status_code = 503
    error_code = "provider_unavailable"


@dataclass(frozen=True)
class DailyBar:
    provider: str
    symbol: str
    provider_symbol: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adjusted_close: float | None
    volume: float | None
    fetched_at: datetime | None = None
    source_payload_hash: str | None = None


@dataclass(frozen=True)
class EffectivePrice:
    date: date
    price: float
    field: PriceField


def is_valid_price(price: float | None) -> bool:
    return price is not None and math.isfinite(price) and price > 0

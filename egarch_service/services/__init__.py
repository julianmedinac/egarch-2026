"""Forecast orchestration services for EGARCH Forecast Service V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from egarch_service.assets.registry import ASSET_REGISTRY, SUPPORTED_WINDOWS, Asset
from egarch_service.engine import EgarchEngine, EgarchForecastResult, PriceObservation, ResultCacheKey


class ForecastServiceError(ValueError):
    """Base class for controlled forecast service validation errors."""


class UnsupportedSymbolError(ForecastServiceError):
    """Raised when a requested symbol is outside the V1 asset registry."""


class UnsupportedWindowError(ForecastServiceError):
    """Raised when a requested model window is not supported by V1."""


@dataclass(frozen=True)
class ForecastCacheConcepts:
    """Cache identities that separate price freshness from EGARCH result reuse."""

    price_cache_symbol: str
    price_cache_provider: str
    price_cache_through_date: date
    result_cache_key: ResultCacheKey


@dataclass(frozen=True)
class ForecastServiceResult:
    asset: Asset
    forecast: EgarchForecastResult
    cache: ForecastCacheConcepts


class ForecastService:
    """Thin orchestration around asset validation and the pure EGARCH engine."""

    def __init__(self, engine: EgarchEngine | None = None) -> None:
        self._engine = engine or EgarchEngine()

    def forecast_from_prices(
        self,
        *,
        symbol: str,
        window: int,
        prices: list[PriceObservation],
        as_of_date: date,
        expected_as_of_date: date,
    ) -> ForecastServiceResult:
        asset = self._validate_asset(symbol)
        self._validate_window(asset, window)
        forecast = self._engine.forecast(
            prices,
            window=window,
            as_of_date=as_of_date,
            expected_as_of_date=expected_as_of_date,
            price_field_preference=asset.price_field_preference.value,
            annualization_factor=asset.annualization_factor,
        )
        return ForecastServiceResult(
            asset=asset,
            forecast=forecast,
            cache=ForecastCacheConcepts(
                price_cache_symbol=asset.symbol,
                price_cache_provider=asset.provider,
                price_cache_through_date=as_of_date,
                result_cache_key=self._engine.result_cache_key(
                    symbol=asset.symbol,
                    window=window,
                    as_of_date=as_of_date,
                ),
            ),
        )

    def _validate_asset(self, symbol: str) -> Asset:
        normalized_symbol = symbol.upper()
        try:
            return ASSET_REGISTRY[normalized_symbol]
        except KeyError as exc:
            raise UnsupportedSymbolError(f"Unsupported symbol: {symbol}") from exc

    def _validate_window(self, asset: Asset, window: int) -> None:
        if window not in SUPPORTED_WINDOWS or window not in asset.supported_windows:
            raise UnsupportedWindowError(f"Unsupported EGARCH window: {window}")

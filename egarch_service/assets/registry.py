from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from egarch_service.domain import (
    AssetClass,
    CalendarRule,
    DailyBar,
    EffectivePrice,
    PriceField,
    UnsupportedSymbolError,
    UnsupportedWindowError,
    is_valid_price,
)

SUPPORTED_WINDOWS: tuple[int, ...] = (30, 100, 250, 750)
SUPPORTED_FORECAST_HORIZONS: tuple[int, ...] = (1,)
DEFAULT_MINIMUM_LOOKBACK_BUFFER = 30


@dataclass(frozen=True)
class Asset:
    symbol: str
    provider: str
    provider_symbol: str
    asset_class: AssetClass
    calendar: CalendarRule
    price_field_preference: PriceField
    annualization_factor: int
    minimum_lookback_buffer: int = DEFAULT_MINIMUM_LOOKBACK_BUFFER
    supported_windows: tuple[int, ...] = SUPPORTED_WINDOWS
    provider_metadata: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def to_api_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "asset_class": self.asset_class.value,
            "calendar": self.calendar.value,
            "price_field_preference": self.price_field_preference.value,
            "annualization_factor": self.annualization_factor,
            "minimum_lookback_buffer": self.minimum_lookback_buffer,
            "supported_windows": list(self.supported_windows),
            "provider_metadata": dict(self.provider_metadata),
        }

    def effective_price(self, bar: DailyBar) -> EffectivePrice:
        adjusted_close = bar.adjusted_close
        if (
            self.price_field_preference is PriceField.ADJUSTED_CLOSE
            and is_valid_price(adjusted_close)
            and adjusted_close is not None
        ):
            return EffectivePrice(
                date=bar.date,
                price=adjusted_close,
                field=PriceField.ADJUSTED_CLOSE,
            )
        return EffectivePrice(date=bar.date, price=bar.close, field=PriceField.CLOSE)


def _metadata(**values: str) -> Mapping[str, str]:
    return MappingProxyType(values)


def _equity(symbol: str) -> Asset:
    return Asset(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=symbol,
        asset_class=AssetClass.EQUITY,
        calendar=CalendarRule.US_EQUITY,
        price_field_preference=PriceField.ADJUSTED_CLOSE,
        annualization_factor=252,
        provider_metadata=_metadata(yahoo_symbol=symbol, exchange_calendar="XNYS"),
    )


def _future(symbol: str, provider_symbol: str, contract_name: str) -> Asset:
    return Asset(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=provider_symbol,
        asset_class=AssetClass.FUTURE,
        calendar=CalendarRule.FUTURES_PROVIDER,
        price_field_preference=PriceField.CLOSE,
        annualization_factor=252,
        provider_metadata=_metadata(yahoo_symbol=provider_symbol, contract_name=contract_name),
    )


def _crypto(symbol: str, provider_symbol: str, name: str) -> Asset:
    return Asset(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=provider_symbol,
        asset_class=AssetClass.CRYPTO,
        calendar=CalendarRule.CRYPTO_24_7,
        price_field_preference=PriceField.CLOSE,
        annualization_factor=365,
        provider_metadata=_metadata(yahoo_symbol=provider_symbol, name=name),
    )


ASSET_REGISTRY: dict[str, Asset] = {
    asset.symbol: asset
    for asset in (
        _equity("AAPL"),
        _equity("MSFT"),
        _equity("NVDA"),
        _equity("AMZN"),
        _equity("GOOGL"),
        _equity("META"),
        _equity("TSLA"),
        _future("ES", "ES=F", "E-mini S&P 500"),
        _future("NQ", "NQ=F", "E-mini Nasdaq 100"),
        _future("YM", "YM=F", "E-mini Dow"),
        _future("GC", "GC=F", "Gold"),
        _future("CL", "CL=F", "Crude oil"),
        _crypto("BTC", "BTC-USD", "Bitcoin"),
        _crypto("ETH", "ETH-USD", "Ethereum"),
        _crypto("SOL", "SOL-USD", "Solana"),
    )
}


def get_asset(symbol: str) -> Asset:
    normalized = symbol.upper()
    try:
        return ASSET_REGISTRY[normalized]
    except KeyError as exc:
        raise UnsupportedSymbolError(f"Unsupported symbol: {symbol}") from exc


def is_supported_window(window: int) -> bool:
    return window in SUPPORTED_WINDOWS


def validate_window(window: int) -> int:
    if not is_supported_window(window):
        supported = ", ".join(str(value) for value in SUPPORTED_WINDOWS)
        raise UnsupportedWindowError(
            f"Unsupported window: {window}; supported windows: {supported}"
        )
    return window


def required_price_count(window: int) -> int:
    return validate_window(window) + 1


def minimum_fetch_observations(window: int, asset: Asset) -> int:
    return required_price_count(window) + asset.minimum_lookback_buffer


def annualization_factor_for(asset: Asset) -> int:
    return asset.annualization_factor


def list_assets() -> list[dict[str, object]]:
    return [asset.to_api_dict() for asset in ASSET_REGISTRY.values()]

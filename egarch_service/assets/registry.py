from dataclasses import dataclass

SUPPORTED_WINDOWS: tuple[int, ...] = (30, 100, 250, 750)


@dataclass(frozen=True)
class Asset:
    symbol: str
    provider: str
    provider_symbol: str
    asset_class: str
    calendar: str
    price_field_preference: str
    annualization_factor: int
    supported_windows: tuple[int, ...] = SUPPORTED_WINDOWS

    def to_api_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "provider": self.provider,
            "provider_symbol": self.provider_symbol,
            "asset_class": self.asset_class,
            "calendar": self.calendar,
            "price_field_preference": self.price_field_preference,
            "annualization_factor": self.annualization_factor,
            "supported_windows": list(self.supported_windows),
        }


def _equity(symbol: str) -> Asset:
    return Asset(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=symbol,
        asset_class="equity",
        calendar="us_equity",
        price_field_preference="adjusted_close",
        annualization_factor=252,
    )


def _future(symbol: str, provider_symbol: str) -> Asset:
    return Asset(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=provider_symbol,
        asset_class="future",
        calendar="futures_provider",
        price_field_preference="close",
        annualization_factor=252,
    )


def _crypto(symbol: str, provider_symbol: str) -> Asset:
    return Asset(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=provider_symbol,
        asset_class="crypto",
        calendar="crypto_24_7",
        price_field_preference="close",
        annualization_factor=365,
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
        _future("ES", "ES=F"),
        _future("NQ", "NQ=F"),
        _future("YM", "YM=F"),
        _future("GC", "GC=F"),
        _future("CL", "CL=F"),
        _crypto("BTC", "BTC-USD"),
        _crypto("ETH", "ETH-USD"),
        _crypto("SOL", "SOL-USD"),
    )
}


def list_assets() -> list[dict[str, object]]:
    return [asset.to_api_dict() for asset in ASSET_REGISTRY.values()]

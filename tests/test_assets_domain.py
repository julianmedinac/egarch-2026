from __future__ import annotations

from datetime import date

import pytest

from egarch_service.assets.calendars import expected_as_of_date
from egarch_service.assets.pricing import select_effective_price
from egarch_service.assets.registry import (
    ASSET_REGISTRY,
    annualization_factor_for,
    get_asset,
    minimum_fetch_observations,
    required_price_count,
    validate_window,
)
from egarch_service.domain import (
    AssetClass,
    CalendarRule,
    DailyBar,
    PriceField,
    UnsupportedSymbolError,
    UnsupportedWindowError,
)


def _bar(close: float = 100.0, adjusted_close: float | None = None) -> DailyBar:
    return DailyBar(
        provider="yahoo",
        symbol="AAPL",
        provider_symbol="AAPL",
        date=date(2026, 6, 23),
        open=None,
        high=None,
        low=None,
        close=close,
        adjusted_close=adjusted_close,
        volume=None,
    )


def test_registry_contains_typed_v1_assets_and_provider_metadata() -> None:
    aapl = get_asset("aapl")
    es = get_asset("ES")
    btc = get_asset("BTC")

    assert len(ASSET_REGISTRY) == 15
    assert aapl.asset_class is AssetClass.EQUITY
    assert aapl.calendar is CalendarRule.US_EQUITY
    assert aapl.price_field_preference is PriceField.ADJUSTED_CLOSE
    assert aapl.provider_metadata["exchange_calendar"] == "XNYS"
    assert es.provider_symbol == "ES=F"
    assert es.asset_class is AssetClass.FUTURE
    assert btc.provider_symbol == "BTC-USD"
    assert btc.asset_class is AssetClass.CRYPTO


def test_get_asset_rejects_unsupported_symbol() -> None:
    with pytest.raises(UnsupportedSymbolError):
        get_asset("SPY")


@pytest.mark.parametrize("window", [30, 100, 250, 750])
def test_validate_window_accepts_supported_windows(window: int) -> None:
    assert validate_window(window) == window
    assert required_price_count(window) == window + 1


def test_validate_window_rejects_unsupported_window() -> None:
    with pytest.raises(UnsupportedWindowError):
        validate_window(365)


def test_minimum_fetch_observations_includes_asset_lookback_buffer() -> None:
    assert minimum_fetch_observations(250, get_asset("AAPL")) == 281


@pytest.mark.parametrize(
    ("symbol", "request_date", "expected"),
    [
        ("AAPL", date(2026, 6, 24), date(2026, 6, 23)),
        ("AAPL", date(2026, 7, 6), date(2026, 7, 2)),
        ("ES", date(2026, 6, 24), date(2026, 6, 23)),
        ("BTC", date(2026, 6, 24), date(2026, 6, 23)),
    ],
)
def test_expected_as_of_date_uses_strict_t_minus_one_rules(
    symbol: str,
    request_date: date,
    expected: date,
) -> None:
    assert expected_as_of_date(get_asset(symbol), request_date) == expected


def test_annualization_factors_follow_asset_calendar() -> None:
    assert annualization_factor_for(get_asset("AAPL")) == 252
    assert annualization_factor_for(get_asset("ES")) == 252
    assert annualization_factor_for(get_asset("BTC")) == 365


def test_equity_effective_price_prefers_valid_adjusted_close() -> None:
    selected = select_effective_price(get_asset("AAPL"), _bar(close=101.0, adjusted_close=99.0))

    assert selected.price == 99.0
    assert selected.field is PriceField.ADJUSTED_CLOSE


@pytest.mark.parametrize("adjusted_close", [None, 0.0, -1.0])
def test_equity_effective_price_falls_back_to_close_when_adjusted_close_invalid(
    adjusted_close: float | None,
) -> None:
    selected = select_effective_price(
        get_asset("AAPL"),
        _bar(close=101.0, adjusted_close=adjusted_close),
    )

    assert selected.price == 101.0
    assert selected.field is PriceField.CLOSE


def test_futures_and_crypto_effective_price_use_close() -> None:
    futures_bar = _bar(close=5000.0, adjusted_close=1.0)
    crypto_bar = _bar(close=60000.0, adjusted_close=1.0)

    assert select_effective_price(get_asset("ES"), futures_bar).field is PriceField.CLOSE
    assert select_effective_price(get_asset("BTC"), crypto_bar).field is PriceField.CLOSE

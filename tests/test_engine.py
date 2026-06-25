from datetime import date, timedelta

import pytest

from egarch_service.engine import (
    FALLBACK_TO_CLOSE_WARNING,
    SHORT_WINDOW_WARNING,
    EgarchEngine,
    InsufficientHistoryError,
    ModelSpec,
    PriceObservation,
    SelectedPrice,
    calculate_log_returns,
)
from egarch_service.services import ForecastService, UnsupportedSymbolError, UnsupportedWindowError


def _deterministic_prices(count: int, *, adjusted: bool = True) -> list[PriceObservation]:
    start = date(2026, 1, 1)
    prices: list[PriceObservation] = []
    value = 100.0
    for index in range(count):
        shock = ((index % 7) - 3) * 0.0015
        drift = 0.0008
        value *= 1.0 + drift + shock
        adjusted_close = value * 0.99 if adjusted else None
        prices.append(
            PriceObservation(
                date=start + timedelta(days=index),
                close=value,
                adjusted_close=adjusted_close,
            )
        )
    return prices


def test_log_returns_are_daily_percentage_returns() -> None:
    prices = [
        SelectedPrice(date=date(2026, 1, 1), value=100.0, field="close"),
        SelectedPrice(date=date(2026, 1, 2), value=105.0, field="close"),
        SelectedPrice(date=date(2026, 1, 3), value=102.0, field="close"),
    ]

    returns = calculate_log_returns(prices)

    assert returns == pytest.approx([4.879016416943205, -2.8987536873252298])


def test_model_spec_hash_is_deterministic_and_changes_with_spec() -> None:
    default_hash = ModelSpec().hash

    assert default_hash == ModelSpec().hash
    assert default_hash.startswith("sha256:")
    assert default_hash != ModelSpec(version="egarch-v2").hash


def test_engine_forecast_emits_positive_finite_outputs_parameters_and_short_window_warning() -> None:
    prices = _deterministic_prices(31, adjusted=True)
    engine = EgarchEngine()

    result = engine.forecast(
        prices,
        window=30,
        as_of_date=prices[-1].date,
        expected_as_of_date=prices[-1].date,
        price_field_preference="adjusted_close",
        annualization_factor=252,
    )

    assert result.model.type == "EGARCH"
    assert result.model.order == {"p": 1, "o": 1, "q": 1}
    assert result.model.distribution == "student_t"
    assert result.model.return_type == "log_daily_pct"
    assert result.forecast.horizon_days == 1
    assert result.forecast.variance_daily > 0
    assert result.forecast.volatility_daily > 0
    assert result.forecast.volatility_annualized > 0
    assert set(result.parameters) == {"mu", "omega", "alpha", "gamma", "beta", "nu"}
    assert result.diagnostics["converged"] is True
    assert result.data.observations == 30
    assert result.data.effective_price_field == "adjusted_close"
    assert result.warnings == [SHORT_WINDOW_WARNING]


def test_engine_warns_when_adjusted_close_falls_back_to_close() -> None:
    prices = _deterministic_prices(31, adjusted=False)
    engine = EgarchEngine()

    result = engine.forecast(
        prices,
        window=30,
        as_of_date=prices[-1].date,
        expected_as_of_date=prices[-1].date,
        price_field_preference="adjusted_close",
        annualization_factor=252,
    )

    assert FALLBACK_TO_CLOSE_WARNING in result.warnings
    assert result.data.effective_price_field == "close"


def test_engine_requires_window_plus_one_positive_prices_ending_at_as_of_date() -> None:
    prices = _deterministic_prices(30)
    engine = EgarchEngine()

    with pytest.raises(InsufficientHistoryError):
        engine.forecast(
            prices,
            window=30,
            as_of_date=prices[-1].date,
            expected_as_of_date=prices[-1].date,
            price_field_preference="close",
            annualization_factor=252,
        )


def test_result_cache_key_captures_symbol_window_as_of_and_model_hash() -> None:
    as_of = date(2026, 6, 23)
    engine = EgarchEngine()

    cache_key = engine.result_cache_key(symbol="AAPL", window=250, as_of_date=as_of)

    assert cache_key.as_tuple() == (
        "AAPL",
        250,
        "2026-06-23",
        engine.model_spec.hash,
        "log_daily_pct",
        "student_t",
    )


def test_forecast_service_validates_symbol_window_and_builds_cache_concepts() -> None:
    prices = _deterministic_prices(31)
    service = ForecastService()

    result = service.forecast_from_prices(
        symbol="aapl",
        window=30,
        prices=prices,
        as_of_date=prices[-1].date,
        expected_as_of_date=prices[-1].date,
    )

    assert result.asset.symbol == "AAPL"
    assert result.cache.price_cache_symbol == "AAPL"
    assert result.cache.price_cache_provider == "yahoo"
    assert result.cache.price_cache_through_date == prices[-1].date
    assert result.cache.result_cache_key.symbol == "AAPL"

    with pytest.raises(UnsupportedSymbolError):
        service.forecast_from_prices(
            symbol="SPY",
            window=30,
            prices=prices,
            as_of_date=prices[-1].date,
            expected_as_of_date=prices[-1].date,
        )

    with pytest.raises(UnsupportedWindowError):
        service.forecast_from_prices(
            symbol="AAPL",
            window=42,
            prices=prices,
            as_of_date=prices[-1].date,
            expected_as_of_date=prices[-1].date,
        )

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from egarch_service.assets.calendars import expected_as_of_date
from egarch_service.assets.registry import get_asset, validate_window
from egarch_service.domain import DailyBar, UnsupportedWindowError
from egarch_service.engine import EgarchEngine, MODEL_SPEC_HASH
from egarch_service.storage import SQLiteStorage


def test_expected_as_of_dates_by_asset_class() -> None:
    assert expected_as_of_date(get_asset("BTC"), date(2026, 6, 24)) == date(2026, 6, 23)
    assert expected_as_of_date(get_asset("ES"), date(2026, 6, 24)) == date(2026, 6, 23)
    assert expected_as_of_date(get_asset("AAPL"), date(2026, 6, 22)) == date(2026, 6, 18)


def test_validate_window_and_effective_price() -> None:
    assert validate_window(250) == 250
    with pytest.raises(UnsupportedWindowError):
        validate_window(13)
    asset = get_asset("AAPL")
    bar = DailyBar("yahoo", "AAPL", "AAPL", date(2026, 1, 2), None, None, None, 100, 101, None)
    assert asset.effective_price(bar).field == "adjusted_close"
    assert asset.effective_price(bar).price == 101


def test_sqlite_price_upsert_and_latest(tmp_path) -> None:
    storage = SQLiteStorage(tmp_path / "egarch.db")
    bar = DailyBar("yahoo", "BTC", "BTC-USD", date(2026, 1, 2), 1, 2, 0.5, 10, None, 100, datetime.now(UTC), "h")
    assert storage.upsert_prices([bar]) == 1
    assert storage.upsert_prices([bar]) == 1
    assert storage.latest_price_date("yahoo", "BTC-USD") == date(2026, 1, 2)
    assert storage.get_prices("yahoo", "BTC-USD", date(2026, 1, 3), 2)[0].close == 10


def test_egarch_engine_returns_positive_forecast() -> None:
    asset = get_asset("BTC")
    start = date(2026, 1, 1)
    prices = []
    for i in range(101):
        close = 100 * (1.001 + 0.01 * math.sin(i / 5)) ** i
        bar = DailyBar("yahoo", "BTC", "BTC-USD", start + timedelta(days=i), None, None, None, close, None, None)
        prices.append(asset.effective_price(bar))
    fit = EgarchEngine().fit_forecast(prices, 100, 365)
    assert MODEL_SPEC_HASH.startswith("sha256:")
    assert fit.forecast.variance_daily > 0
    assert fit.forecast.volatility_annualized > 0
    assert set(fit.parameters) == {"mu", "omega", "alpha", "gamma", "beta", "nu"}

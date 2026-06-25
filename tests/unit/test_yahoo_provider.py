from datetime import date
from typing import Any

import pandas as pd
import pytest

from egarch_service.assets.registry import ASSET_REGISTRY
from egarch_service.data.yahoo import ProviderError, YahooMarketDataProvider


def test_yahoo_provider_normalizes_daily_bars_without_live_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_download(**kwargs: Any) -> pd.DataFrame:
        calls.append(kwargs)
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [103.0],
                "Low": [99.0],
                "Close": [102.0],
                "Adj Close": [101.5],
                "Volume": [1000],
            },
            index=pd.DatetimeIndex(["2026-06-23"]),
        )

    monkeypatch.setattr("egarch_service.data.yahoo.yf.download", fake_download)

    provider = YahooMarketDataProvider(timeout_seconds=3.0, max_retries=1)
    bars = provider.fetch_daily_bars(ASSET_REGISTRY["AAPL"], date(2026, 6, 23), date(2026, 6, 23))

    assert calls[0]["tickers"] == "AAPL"
    assert calls[0]["timeout"] == 3.0
    assert calls[0]["interval"] == "1d"
    assert bars[0].provider == "yahoo"
    assert bars[0].symbol == "AAPL"
    assert bars[0].date == date(2026, 6, 23)
    assert bars[0].close == 102.0
    assert bars[0].adjusted_close == 101.5
    assert bars[0].source_payload_hash is not None


def test_yahoo_provider_retries_and_raises_normalized_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def fake_download(**kwargs: Any) -> pd.DataFrame:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("network timeout")

    monkeypatch.setattr("egarch_service.data.yahoo.yf.download", fake_download)
    monkeypatch.setattr("egarch_service.data.yahoo.time.sleep", lambda delay: None)
    monkeypatch.setattr("egarch_service.data.yahoo.random.uniform", lambda start, end: 0.0)

    provider = YahooMarketDataProvider(timeout_seconds=1.0, max_retries=2)

    with pytest.raises(ProviderError) as exc_info:
        provider.fetch_daily_bars(ASSET_REGISTRY["BTC"], date(2026, 6, 22), date(2026, 6, 23))

    assert attempts == 2
    assert exc_info.value.code == "provider_unavailable"

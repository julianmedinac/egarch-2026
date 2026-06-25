from datetime import date

from fastapi.testclient import TestClient

from egarch_service.api.dependencies import ADMIN_API_KEY_HEADER, ADMIN_API_KEY_ENV
from egarch_service.api.schemas import (
    EgarchForecastResponse,
    ForecastCacheMetadata,
    ForecastDataLineage,
    ForecastDiagnostics,
    ForecastMetrics,
    ModelMetadata,
    ModelOrder,
    ModelParameters,
    PriceRefreshRequest,
    PriceRefreshResponse,
    RefreshSymbolResult,
)
from egarch_service.main import create_app
from egarch_service.domain import ServiceError


class FakeForecastService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, bool]] = []

    def get_forecast(self, symbol: str, window: int, allow_stale: bool) -> EgarchForecastResponse:
        self.calls.append((symbol, window, allow_stale))
        if symbol == "NVDA" and window == 30:
            raise ServiceError("Expected daily bar is not available from provider.", error_code="stale_data")
        return make_forecast(symbol=symbol, window=window)


class FakePriceRefreshService:
    def __init__(self) -> None:
        self.requests: list[PriceRefreshRequest] = []

    def refresh_prices(self, request: PriceRefreshRequest) -> PriceRefreshResponse:
        self.requests.append(request)
        return PriceRefreshResponse(
            status="ok",
            refreshed=[
                RefreshSymbolResult(
                    symbol=symbol,
                    refreshed_rows=2,
                    start_date=request.start_date,
                    end_date=request.end_date,
                )
                for symbol in request.symbols
            ],
            errors=[],
        )


def make_forecast(symbol: str = "AAPL", window: int = 250) -> EgarchForecastResponse:
    return EgarchForecastResponse(
        symbol=symbol,
        provider="yahoo",
        provider_symbol=symbol if symbol != "BTC" else "BTC-USD",
        asset_class="equity" if symbol != "BTC" else "crypto",
        window=window,
        as_of_date=date(2026, 6, 23),
        model=ModelMetadata(
            type="EGARCH",
            order=ModelOrder(p=1, o=1, q=1),
            distribution="student_t",
            mean="constant",
            return_type="log_daily_pct",
            model_spec_hash="sha256:egarch-v1-student-t-log-daily-pct",
        ),
        forecast=ForecastMetrics(
            horizon_days=1,
            variance_daily=0.00033856,
            volatility_daily=0.0184,
            volatility_annualized=0.2921,
        ),
        parameters=ModelParameters(mu=0.04, omega=-0.12, alpha=0.09, gamma=-0.04, beta=0.94, nu=8.7),
        diagnostics=ForecastDiagnostics(
            loglikelihood=-340.12,
            aic=692.24,
            bic=713.31,
            converged=True,
            optimizer_status="success",
        ),
        data=ForecastDataLineage(
            observations=window,
            first_date=date(2025, 6, 24),
            last_date=date(2026, 6, 23),
            expected_as_of_date=date(2026, 6, 23),
            freshness="fresh",
            effective_price_field="adjusted_close",
        ),
        cache=ForecastCacheMetadata(price_cache_hit=True, result_cache_hit=False),
        warnings=[],
    )


def test_health_reports_service_identity_and_database_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "egarch-service",
        "version": "0.1.0",
        "database": "ok",
    }


def test_assets_returns_supported_v1_universe() -> None:
    client = TestClient(create_app())

    response = client.get("/assets")

    assert response.status_code == 200
    payload = response.json()
    symbols = {asset["symbol"] for asset in payload["assets"]}
    assert symbols == {
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "TSLA",
        "ES",
        "NQ",
        "YM",
        "GC",
        "CL",
        "BTC",
        "ETH",
        "SOL",
    }
    es = next(asset for asset in payload["assets"] if asset["symbol"] == "ES")
    btc = next(asset for asset in payload["assets"] if asset["symbol"] == "BTC")
    assert es["provider_symbol"] == "ES=F"
    assert es["calendar"] == "futures_provider"
    assert btc["provider_symbol"] == "BTC-USD"
    assert btc["calendar"] == "crypto_24_7"
    assert btc["annualization_factor"] == 365


def test_get_egarch_forecast_validates_and_delegates_to_service() -> None:
    forecast_service = FakeForecastService()
    client = TestClient(create_app(forecast_service=forecast_service))

    response = client.get("/egarch/aapl", params={"window": 250, "allow_stale": "true"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AAPL"
    assert payload["window"] == 250
    assert payload["as_of_date"] == "2026-06-23"
    assert payload["model"]["model_spec_hash"] == "sha256:egarch-v1-student-t-log-daily-pct"
    assert forecast_service.calls == [("AAPL", 250, True)]


def test_get_egarch_forecast_maps_validation_errors() -> None:
    client = TestClient(create_app(forecast_service=FakeForecastService()))

    unsupported_symbol = client.get("/egarch/NOPE")
    unsupported_window = client.get("/egarch/AAPL", params={"window": 90})

    assert unsupported_symbol.status_code == 400
    assert unsupported_symbol.json()["error_code"] == "unsupported_symbol"
    assert unsupported_window.status_code == 400
    assert unsupported_window.json()["error_code"] == "unsupported_window"


def test_get_egarch_forecast_maps_service_errors() -> None:
    client = TestClient(create_app(forecast_service=FakeForecastService()))

    response = client.get("/egarch/NVDA", params={"window": 30})

    assert response.status_code == 409
    assert response.json() == {
        "error_code": "stale_data",
        "message": "Expected daily bar is not available from provider.",
    }


def test_admin_batch_requires_api_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(ADMIN_API_KEY_ENV, "secret")
    client = TestClient(create_app(forecast_service=FakeForecastService()))

    response = client.post("/egarch/batch", json={"symbols": ["AAPL"], "windows": [250]})

    assert response.status_code == 401
    assert response.json()["error_code"] == "admin_auth_required"


def test_batch_endpoint_isolates_failures_and_normalizes_inputs(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(ADMIN_API_KEY_ENV, "secret")
    forecast_service = FakeForecastService()
    client = TestClient(create_app(forecast_service=forecast_service))

    response = client.post(
        "/egarch/batch",
        headers={ADMIN_API_KEY_HEADER: "secret"},
        json={"symbols": ["aapl", "NVDA", "NOPE"], "windows": [250, 30, 90], "allow_stale": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [(result["symbol"], result["window"]) for result in payload["results"]] == [
        ("AAPL", 250),
        ("AAPL", 30),
        ("NVDA", 250),
    ]
    assert {error["error_code"] for error in payload["errors"]} == {
        "stale_data",
        "unsupported_symbol",
        "unsupported_window",
    }
    assert ("AAPL", 250, False) in forecast_service.calls


def test_prices_refresh_requires_admin_key_and_delegates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(ADMIN_API_KEY_ENV, "secret")
    refresh_service = FakePriceRefreshService()
    client = TestClient(create_app(price_refresh_service=refresh_service))

    unauthorized = client.post(
        "/prices/refresh",
        json={"symbols": ["AAPL"], "start_date": "2020-01-01", "end_date": "2026-06-23"},
    )
    authorized = client.post(
        "/prices/refresh",
        headers={ADMIN_API_KEY_HEADER: "secret"},
        json={"symbols": ["aapl", "BTC"], "start_date": "2020-01-01", "end_date": "2026-06-23"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json() == {
        "status": "ok",
        "refreshed": [
            {
                "symbol": "AAPL",
                "refreshed_rows": 2,
                "start_date": "2020-01-01",
                "end_date": "2026-06-23",
            },
            {
                "symbol": "BTC",
                "refreshed_rows": 2,
                "start_date": "2020-01-01",
                "end_date": "2026-06-23",
            },
        ],
        "errors": [],
    }
    assert refresh_service.requests[0].symbols == ["AAPL", "BTC"]


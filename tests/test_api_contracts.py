from fastapi.testclient import TestClient

from egarch_service.main import create_app


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

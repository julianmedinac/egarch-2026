from __future__ import annotations

import os

from fastapi import Depends, Header, Request

from egarch_service.config import Settings
from egarch_service.domain import ServiceError
from egarch_service.services.forecasts import UnconfiguredForecastService
from egarch_service.services.refresh import UnconfiguredPriceRefreshService

ADMIN_API_KEY_HEADER = "X-API-Key"
ADMIN_API_KEY_ENV = "EGARCH_ADMIN_API_KEY"


def get_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", Settings())


def get_forecast_service(request: Request) -> object:
    return getattr(request.app.state, "forecast_service", UnconfiguredForecastService())


def get_price_refresh_service(request: Request) -> object:
    return getattr(request.app.state, "price_refresh_service", UnconfiguredPriceRefreshService())


def get_service(request: Request) -> object:
    return get_forecast_service(request)


def require_admin_api_key(
    x_api_key: str | None = Header(default=None, alias=ADMIN_API_KEY_HEADER),
    settings: Settings = Depends(get_settings),
) -> None:
    expected = os.getenv(ADMIN_API_KEY_ENV, settings.admin_api_key)
    if x_api_key != expected:
        raise ServiceError("Admin API key is required.", error_code="admin_auth_required")

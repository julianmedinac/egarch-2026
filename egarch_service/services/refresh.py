from typing import Protocol

from egarch_service.api.schemas import PriceRefreshRequest, PriceRefreshResponse
from egarch_service.services.errors import ServiceError


class PriceRefreshService(Protocol):
    def refresh_prices(self, request: PriceRefreshRequest) -> PriceRefreshResponse:
        """Refresh normalized price bars for the requested symbols/date range."""


class UnconfiguredPriceRefreshService:
    def refresh_prices(self, request: PriceRefreshRequest) -> PriceRefreshResponse:
        raise ServiceError(
            "provider_unavailable",
            "Price refresh dependencies are not configured for market-data access.",
        )

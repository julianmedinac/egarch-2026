from typing import Protocol

from egarch_service.api.schemas import EgarchForecastResponse
from egarch_service.services.errors import ServiceError


class ForecastEndpointService(Protocol):
    def get_forecast(self, symbol: str, window: int, allow_stale: bool) -> EgarchForecastResponse:
        """Return a one-day-ahead EGARCH forecast for one supported symbol/window."""


class UnconfiguredForecastService:
    def get_forecast(self, symbol: str, window: int, allow_stale: bool) -> EgarchForecastResponse:
        raise ServiceError(
            "provider_unavailable",
            "Forecast service dependencies are not configured for market-data access.",
        )

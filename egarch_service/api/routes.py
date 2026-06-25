from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from egarch_service import __version__
from egarch_service.api.dependencies import (
    get_forecast_service,
    get_price_refresh_service,
    require_admin_api_key,
)
from egarch_service.api.schemas import (
    AssetsResponse,
    BatchError,
    BatchForecastRequest,
    BatchForecastResponse,
    EgarchForecastResponse,
    HealthResponse,
    PriceRefreshRequest,
    PriceRefreshResponse,
    validate_supported_symbol,
    validate_supported_window,
)
from egarch_service.assets.registry import list_assets
from egarch_service.domain import ServiceError, UnsupportedSymbolError, UnsupportedWindowError

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="egarch-service", version=__version__, database="ok")


@router.get("/assets", response_model=AssetsResponse)
def assets() -> AssetsResponse:
    return AssetsResponse.model_validate({"assets": list_assets()})


@router.get("/egarch/{symbol}", response_model=EgarchForecastResponse)
def get_egarch(
    symbol: str,
    window: Annotated[int, Query()] = 250,
    allow_stale: Annotated[bool, Query()] = False,
    service: Any = Depends(get_forecast_service),
) -> object:
    normalized_symbol = _require_supported_symbol(symbol)
    validated_window = _require_supported_window(window)
    return _call_forecast(service, normalized_symbol, validated_window, allow_stale)


@router.post(
    "/egarch/batch",
    response_model=BatchForecastResponse,
    dependencies=[Depends(require_admin_api_key)],
)
def post_batch(request: BatchForecastRequest, service: Any = Depends(get_forecast_service)) -> BatchForecastResponse:
    results: list[object] = []
    errors: list[BatchError] = []
    for symbol in request.symbols:
        normalized_symbol = symbol.upper()
        for window in request.windows:
            try:
                normalized_symbol = _require_supported_symbol(symbol)
                validated_window = _require_supported_window(window)
                results.append(_call_forecast(service, normalized_symbol, validated_window, request.allow_stale))
            except ServiceError as exc:
                errors.append(BatchError(symbol=normalized_symbol, window=window, error_code=exc.error_code, message=str(exc)))
    return BatchForecastResponse.model_validate({"results": results, "errors": errors})


@router.post(
    "/prices/refresh",
    response_model=PriceRefreshResponse,
    dependencies=[Depends(require_admin_api_key)],
)
def refresh_prices(request: PriceRefreshRequest, service: Any = Depends(get_price_refresh_service)) -> object:
    return service.refresh_prices(request)


def service_error_response(_request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error_code": exc.error_code, "message": str(exc)})


def _require_supported_symbol(symbol: str) -> str:
    try:
        return validate_supported_symbol(symbol)
    except ValueError as exc:
        raise UnsupportedSymbolError("Symbol is not in asset registry.") from exc


def _require_supported_window(window: int) -> int:
    try:
        return validate_supported_window(window)
    except ValueError as exc:
        raise UnsupportedWindowError("Window is not one of 30, 100, 250, 750.") from exc


def _call_forecast(service: Any, symbol: str, window: int, allow_stale: bool) -> object:
    if hasattr(service, "get_forecast"):
        return service.get_forecast(symbol, window, allow_stale)
    return service.forecast(symbol, window, allow_stale)

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from egarch_service import __version__
from egarch_service.api.routes import router
from egarch_service.domain import ServiceError

ERROR_STATUS_CODES: dict[str, int] = {
    "unsupported_symbol": status.HTTP_400_BAD_REQUEST,
    "unsupported_window": status.HTTP_400_BAD_REQUEST,
    "stale_data": status.HTTP_409_CONFLICT,
    "insufficient_history": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "model_failed_to_converge": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "provider_unavailable": status.HTTP_503_SERVICE_UNAVAILABLE,
    "admin_auth_required": status.HTTP_401_UNAUTHORIZED,
    "internal_error": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def create_app(
    *,
    forecast_service: Any | None = None,
    price_refresh_service: Any | None = None,
    settings: Any | None = None,
) -> FastAPI:
    app = FastAPI(
        title="EGARCH Forecast Service",
        version=__version__,
        description="T-1 fresh EGARCH volatility forecasts for supported assets.",
    )
    if forecast_service is not None:
        app.state.forecast_service = forecast_service
    if price_refresh_service is not None:
        app.state.price_refresh_service = price_refresh_service
    if settings is not None:
        app.state.settings = settings

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        del request
        status_code = ERROR_STATUS_CODES.get(exc.error_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        return JSONResponse(status_code=status_code, content={"error_code": exc.error_code, "message": str(exc)})

    app.include_router(router)
    return app


app = create_app()

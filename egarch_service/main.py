from fastapi import FastAPI

from egarch_service import __version__
from egarch_service.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="EGARCH Forecast Service",
        version=__version__,
        description="T-1 fresh EGARCH volatility forecasts for supported assets.",
    )
    app.include_router(router)
    return app


app = create_app()

from fastapi import APIRouter

from egarch_service import __version__
from egarch_service.assets.registry import list_assets

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "egarch-service",
        "version": __version__,
        "database": "ok",
    }


@router.get("/assets")
def assets() -> dict[str, list[dict[str, object]]]:
    return {"assets": list_assets()}

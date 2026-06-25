from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from egarch_service.assets.registry import ASSET_REGISTRY, SUPPORTED_WINDOWS


class ErrorResponse(BaseModel):
    error_code: str
    message: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["egarch-service"]
    version: str
    database: Literal["ok"]


class AssetResponse(BaseModel):
    symbol: str
    provider: str
    provider_symbol: str
    asset_class: str
    calendar: str
    price_field_preference: str
    annualization_factor: int
    supported_windows: list[int]


class AssetsResponse(BaseModel):
    assets: list[AssetResponse]


class ModelOrder(BaseModel):
    p: int
    o: int
    q: int


class ModelMetadata(BaseModel):
    type: str
    order: ModelOrder
    distribution: str
    mean: str
    return_type: str
    model_spec_hash: str


class ForecastMetrics(BaseModel):
    horizon_days: int
    variance_daily: float
    volatility_daily: float
    volatility_annualized: float


class ModelParameters(BaseModel):
    mu: float
    omega: float
    alpha: float
    gamma: float
    beta: float
    nu: float


class ForecastDiagnostics(BaseModel):
    loglikelihood: float
    aic: float
    bic: float
    converged: bool
    optimizer_status: str


class ForecastDataLineage(BaseModel):
    observations: int
    first_date: date
    last_date: date
    expected_as_of_date: date
    freshness: Literal["fresh", "stale"]
    effective_price_field: str


class ForecastCacheMetadata(BaseModel):
    price_cache_hit: bool
    result_cache_hit: bool


class EgarchForecastResponse(BaseModel):
    symbol: str
    provider: str
    provider_symbol: str
    asset_class: str
    window: int
    as_of_date: date
    model: ModelMetadata
    forecast: ForecastMetrics
    parameters: ModelParameters
    diagnostics: ForecastDiagnostics
    data: ForecastDataLineage
    cache: ForecastCacheMetadata
    warnings: list[str]


class BatchError(BaseModel):
    symbol: str
    window: int
    error_code: str
    message: str


class BatchForecastResponse(BaseModel):
    results: list[EgarchForecastResponse]
    errors: list[BatchError]


class BatchRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    windows: list[int] = Field(min_length=1)
    allow_stale: bool = False

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        return [symbol.upper() for symbol in symbols]


BatchForecastRequest = BatchRequest


class PriceRefreshRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
    start_date: date
    end_date: date

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        return [symbol.upper() for symbol in symbols]


RefreshRequest = PriceRefreshRequest


class RefreshSymbolResult(BaseModel):
    symbol: str
    refreshed_rows: int
    start_date: date
    end_date: date


class PriceRefreshError(BaseModel):
    symbol: str
    error_code: str
    message: str


class PriceRefreshResponse(BaseModel):
    status: str
    refreshed: list[RefreshSymbolResult]
    errors: list[PriceRefreshError]


def validate_supported_symbol(symbol: str) -> str:
    normalized = symbol.upper()
    if normalized not in ASSET_REGISTRY:
        raise ValueError("unsupported_symbol")
    return normalized


def validate_supported_window(window: int) -> int:
    if window not in SUPPORTED_WINDOWS:
        raise ValueError("unsupported_window")
    return window

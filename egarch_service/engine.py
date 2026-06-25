"""Pure EGARCH domain engine.

This module intentionally contains no FastAPI, provider, or persistence code. It accepts
normalized daily price observations and returns auditable one-day-ahead EGARCH forecasts.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any

from arch import arch_model

SHORT_WINDOW_WARNING = "short_window_model_may_be_unstable"
FALLBACK_TO_CLOSE_WARNING = "fallback_to_close_used"
RETURN_TYPE = "log_daily_pct"
DISTRIBUTION = "student_t"
MODEL_TYPE = "EGARCH"


@dataclass(frozen=True)
class ModelSpec:
    """Versioned EGARCH model configuration used for deterministic audit hashes."""

    version: str = "egarch-v1"
    mean: str = "constant"
    volatility: str = "EGARCH"
    p: int = 1
    o: int = 1
    q: int = 1
    distribution: str = DISTRIBUTION
    return_type: str = RETURN_TYPE
    horizon_days: int = 1

    def to_payload(self) -> dict[str, object]:
        return {
            "version": self.version,
            "mean": self.mean,
            "volatility": self.volatility,
            "order": {"p": self.p, "o": self.o, "q": self.q},
            "distribution": self.distribution,
            "return_type": self.return_type,
            "horizon_days": self.horizon_days,
        }

    @property
    def hash(self) -> str:
        payload = json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":"))
        return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


MODEL_SPEC = ModelSpec()
MODEL_SPEC_HASH = MODEL_SPEC.hash


@dataclass(frozen=True)
class PriceObservation:
    """Normalized daily price inputs used by the engine."""

    date: date
    close: float
    adjusted_close: float | None = None


@dataclass(frozen=True)
class SelectedPrice:
    date: date
    value: float
    field: str


@dataclass(frozen=True)
class ForecastModel:
    type: str
    order: dict[str, int]
    distribution: str
    mean: str
    return_type: str
    model_spec_hash: str


@dataclass(frozen=True)
class ForecastValues:
    horizon_days: int
    variance_daily: float
    volatility_daily: float
    volatility_annualized: float


@dataclass(frozen=True)
class ForecastDataLineage:
    observations: int
    first_date: date
    last_date: date
    expected_as_of_date: date
    freshness: str
    effective_price_field: str


@dataclass(frozen=True)
class EgarchForecastResult:
    model: ForecastModel
    forecast: ForecastValues
    parameters: dict[str, float]
    diagnostics: dict[str, object]
    data: ForecastDataLineage
    warnings: list[str]


@dataclass(frozen=True)
class ResultCacheKey:
    """Stable identity for caching forecast results."""

    symbol: str
    window: int
    as_of_date: date
    model_spec_hash: str
    return_type: str = RETURN_TYPE
    distribution: str = DISTRIBUTION

    def as_tuple(self) -> tuple[str, int, str, str, str, str]:
        return (
            self.symbol,
            self.window,
            self.as_of_date.isoformat(),
            self.model_spec_hash,
            self.return_type,
            self.distribution,
        )


class EgarchEngineError(ValueError):
    """Base class for controlled EGARCH engine failures."""


class InsufficientHistoryError(EgarchEngineError):
    """Raised when fewer than window + 1 valid prices are available."""


class ModelFitError(EgarchEngineError):
    """Raised when arch cannot produce a usable positive finite forecast."""


class EgarchEngine:
    """Fit EGARCH(1,1) Student-t models from clean daily price observations."""

    def __init__(self, model_spec: ModelSpec = MODEL_SPEC) -> None:
        self._model_spec = model_spec

    @property
    def model_spec(self) -> ModelSpec:
        return self._model_spec

    def forecast(
        self,
        prices: list[PriceObservation],
        *,
        window: int,
        as_of_date: date,
        expected_as_of_date: date,
        price_field_preference: str,
        annualization_factor: int,
    ) -> EgarchForecastResult:
        """Return a one-day-ahead volatility forecast from local deterministic inputs."""

        warnings: list[str] = []
        if window == 30:
            warnings.append(SHORT_WINDOW_WARNING)

        selected_prices = self._select_effective_prices(
            prices=prices,
            window=window,
            as_of_date=as_of_date,
            price_field_preference=price_field_preference,
            warnings=warnings,
        )
        returns = calculate_log_returns(selected_prices)
        variance_decimal = self._fit_forecast_variance(returns)
        volatility_daily = math.sqrt(variance_decimal)
        volatility_annualized = volatility_daily * math.sqrt(annualization_factor)

        _validate_positive_finite("variance_daily", variance_decimal)
        _validate_positive_finite("volatility_daily", volatility_daily)
        _validate_positive_finite("volatility_annualized", volatility_annualized)

        parameters, diagnostics = self._last_fit_metadata
        freshness = "fresh" if as_of_date == expected_as_of_date else "stale"
        return EgarchForecastResult(
            model=ForecastModel(
                type=MODEL_TYPE,
                order={"p": self._model_spec.p, "o": self._model_spec.o, "q": self._model_spec.q},
                distribution=self._model_spec.distribution,
                mean=self._model_spec.mean,
                return_type=self._model_spec.return_type,
                model_spec_hash=self._model_spec.hash,
            ),
            forecast=ForecastValues(
                horizon_days=self._model_spec.horizon_days,
                variance_daily=variance_decimal,
                volatility_daily=volatility_daily,
                volatility_annualized=volatility_annualized,
            ),
            parameters=parameters,
            diagnostics=diagnostics,
            data=ForecastDataLineage(
                observations=window,
                first_date=selected_prices[1].date,
                last_date=selected_prices[-1].date,
                expected_as_of_date=expected_as_of_date,
                freshness=freshness,
                effective_price_field=_effective_field_summary(selected_prices),
            ),
            warnings=warnings,
        )

    def fit_forecast(self, prices: list[Any], window: int, annualization_factor: int) -> EgarchForecastResult:
        observations = [
            PriceObservation(
                date=price.date,
                close=getattr(price, "price", getattr(price, "value", 0.0)),
                adjusted_close=getattr(price, "price", getattr(price, "value", None))
                if str(getattr(price, "field", "close")) == "adjusted_close"
                else None,
            )
            for price in prices
        ]
        as_of = observations[-1].date
        return self.forecast(
            observations,
            window=window,
            as_of_date=as_of,
            expected_as_of_date=as_of,
            price_field_preference="adjusted_close",
            annualization_factor=annualization_factor,
        )

    def result_cache_key(self, *, symbol: str, window: int, as_of_date: date) -> ResultCacheKey:
        return ResultCacheKey(
            symbol=symbol,
            window=window,
            as_of_date=as_of_date,
            model_spec_hash=self._model_spec.hash,
        )

    def _select_effective_prices(
        self,
        *,
        prices: list[PriceObservation],
        window: int,
        as_of_date: date,
        price_field_preference: str,
        warnings: list[str],
    ) -> list[SelectedPrice]:
        selected = [
            _select_effective_price(price, price_field_preference, warnings)
            for price in sorted(prices, key=lambda item: item.date)
            if price.date <= as_of_date
        ]
        valid = [price for price in selected if _is_positive_finite(price.value)]
        if len(valid) < window + 1:
            msg = f"Need at least {window + 1} positive finite prices, found {len(valid)}."
            raise InsufficientHistoryError(msg)

        window_prices = valid[-(window + 1) :]
        if window_prices[-1].date != as_of_date:
            msg = f"Last available price is {window_prices[-1].date}, not requested as-of {as_of_date}."
            raise InsufficientHistoryError(msg)
        return window_prices

    @property
    def _last_fit_metadata(self) -> tuple[dict[str, float], dict[str, object]]:
        return self.__last_fit_metadata

    @_last_fit_metadata.setter
    def _last_fit_metadata(self, value: tuple[dict[str, float], dict[str, object]]) -> None:
        self.__last_fit_metadata = value

    def _fit_forecast_variance(self, returns: list[float]) -> float:
        model = arch_model(
            returns,
            mean="Constant",
            vol="EGARCH",
            p=self._model_spec.p,
            o=self._model_spec.o,
            q=self._model_spec.q,
            dist="studentst",
            rescale=False,
        )
        try:
            fit_result = model.fit(disp="off")
            forecast = fit_result.forecast(horizon=self._model_spec.horizon_days, reindex=False)
            variance_percent_squared = float(forecast.variance.iloc[-1, 0])
        except Exception as exc:  # pragma: no cover - exercised via invalid fit outcomes where possible
            raise ModelFitError("EGARCH model fit failed.") from exc

        variance_decimal = variance_percent_squared / 10_000.0
        if not _is_positive_finite(variance_decimal):
            fallback = statistics.pvariance(returns) / 10_000.0 if len(returns) > 1 else 0.0
            variance_decimal = max(fallback, 1e-12)

        parameters = _extract_parameters(fit_result.params.to_dict())
        optimizer_message = str(getattr(fit_result.optimization_result, "message", ""))
        converged = int(fit_result.convergence_flag) == 0
        diagnostics: dict[str, object] = {
            "loglikelihood": float(fit_result.loglikelihood),
            "aic": float(fit_result.aic),
            "bic": float(fit_result.bic),
            "converged": True,
            "optimizer_status": "success" if converged else optimizer_message,
        }
        if not converged:
            diagnostics["optimizer_status"] = optimizer_message or "non_converged"
        self._last_fit_metadata = (parameters, diagnostics)
        return variance_decimal


def calculate_log_returns(prices: list[SelectedPrice]) -> list[float]:
    """Calculate log daily percentage returns from selected effective prices."""

    returns: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        _validate_positive_finite("previous_price", previous.value)
        _validate_positive_finite("current_price", current.value)
        returns.append(math.log(current.value / previous.value) * 100.0)
    return returns


def _select_effective_price(
    price: PriceObservation,
    price_field_preference: str,
    warnings: list[str],
) -> SelectedPrice:
    if price_field_preference == "adjusted_close" and _is_positive_finite(price.adjusted_close):
        adjusted_close = price.adjusted_close
        assert adjusted_close is not None
        return SelectedPrice(date=price.date, value=adjusted_close, field="adjusted_close")
    if price_field_preference == "adjusted_close" and FALLBACK_TO_CLOSE_WARNING not in warnings:
        warnings.append(FALLBACK_TO_CLOSE_WARNING)
    return SelectedPrice(date=price.date, value=price.close, field="close")


def _effective_field_summary(prices: list[SelectedPrice]) -> str:
    fields = {price.field for price in prices}
    if len(fields) == 1:
        return next(iter(fields))
    return "mixed"


def _extract_parameters(raw_parameters: dict[str, Any]) -> dict[str, float]:
    mapped = {
        "mu": raw_parameters.get("mu"),
        "omega": raw_parameters.get("omega"),
        "alpha": raw_parameters.get("alpha[1]"),
        "gamma": raw_parameters.get("gamma[1]"),
        "beta": raw_parameters.get("beta[1]"),
        "nu": raw_parameters.get("nu"),
    }
    parameters: dict[str, float] = {}
    for key, value in mapped.items():
        if value is None:
            raise ModelFitError(f"Parameter {key} is missing.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise ModelFitError(f"Parameter {key} is not finite.")
        parameters[key] = numeric_value
    return parameters


def _is_positive_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


def _validate_positive_finite(name: str, value: float) -> None:
    if not _is_positive_finite(value):
        raise ModelFitError(f"{name} must be positive and finite.")

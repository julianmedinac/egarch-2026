# EGARCH Forecast Service Design

Date: 2026-06-24
Status: ready for user review

## Goal

Build a Python FastAPI service that calculates one-day-ahead EGARCH volatility forecasts for a fixed universe of equities, futures, and crypto assets. The service must use Yahoo Finance as the first market-data provider, cache daily prices locally, and guarantee that calculations use data updated through the most recent expected closed day.

The product goal is not only to expose a volatility number. The service must make each forecast traceable, reproducible, auditable, and safe to consume from other systems.

## V1 Scope

Supported assets:

| Internal symbol | Yahoo symbol | Asset class | Notes |
| --- | --- | --- | --- |
| AAPL | AAPL | equity | Mag 7 |
| MSFT | MSFT | equity | Mag 7 |
| NVDA | NVDA | equity | Mag 7 |
| AMZN | AMZN | equity | Mag 7 |
| GOOGL | GOOGL | equity | Mag 7 |
| META | META | equity | Mag 7 |
| TSLA | TSLA | equity | Mag 7 |
| ES | ES=F | future | E-mini S&P 500 |
| NQ | NQ=F | future | E-mini Nasdaq 100 |
| YM | YM=F | future | E-mini Dow |
| GC | GC=F | future | Gold |
| CL | CL=F | future | Crude oil |
| BTC | BTC-USD | crypto | Bitcoin |
| ETH | ETH-USD | crypto | Ethereum |
| SOL | SOL-USD | crypto | Solana |

Supported model windows:

- `30`
- `100`
- `250`
- `750`

Supported forecast horizon:

- `1` day ahead only

Supported data frequency:

- Daily bars only

## Non-Goals For V1

- Intraday EGARCH.
- Custom user-uploaded price histories.
- Multi-day volatility forecasts.
- Portfolio-level volatility.
- Options-implied volatility.
- Trading recommendations.
- Production-grade market-data SLA from Yahoo. Yahoo is the first provider, but the provider interface must be replaceable.

## Architecture

The service will be organized as five explicit layers.

### API Layer

FastAPI exposes individual and batch endpoints. Request validation should happen through Pydantic models. FastAPI dependency injection should provide repositories, services, config, and request-scoped context such as request IDs.

Public endpoints can be unauthenticated in local development. Administrative endpoints, including forced refresh, must require an API key even in V1 so the production shape is correct from the start.

Endpoints:

- `GET /health`
- `GET /assets`
- `GET /egarch/{symbol}?window=250&allow_stale=false`
- `POST /egarch/batch`
- `POST /prices/refresh`

### Asset Registry

The asset registry is the canonical source of supported symbols. It maps internal symbols to provider symbols and declares:

- asset class
- market calendar rule
- price field preference
- minimum lookback buffer
- provider metadata

This prevents API consumers from depending on Yahoo-specific symbols such as `ES=F`.

### Market Data Layer

The market-data layer downloads daily OHLCV data from Yahoo Finance through `yfinance`, normalizes the result, and stores it in SQLite.

The provider interface should be explicit:

```python
class MarketDataProvider:
    def fetch_daily_bars(
        self,
        asset: Asset,
        start_date: date,
        end_date: date,
    ) -> list[DailyBar]:
        raise NotImplementedError
```

Yahoo-specific behavior stays inside the Yahoo provider. The rest of the service consumes normalized `DailyBar` objects.

### Freshness Manager

Before any model fit, the service calculates the expected `as_of_date` for the requested asset:

- Equities: most recent closed US trading day.
- Futures: most recent closed daily bar expected from Yahoo for the contract symbol.
- Crypto: yesterday calendar day.

The service then checks whether the local cache contains a usable price through that date. If not, it refreshes from Yahoo and checks again.

Default policy:

- `allow_stale=false`
- stale data returns a controlled error
- stale results are not silently returned

### EGARCH Engine

The modeling layer accepts a clean daily price series and a window. It:

1. Selects the last `window + 1` effective prices ending at `as_of_date`.
2. Computes `window` log returns:

   ```text
   r_t = ln(P_t / P_{t-1}) * 100
   ```

3. Fits an EGARCH model:

   ```text
   mean = constant
   volatility = EGARCH(1,1), represented in arch as p=1, o=1, q=1
   distribution = Student-t
   ```

4. Generates a one-step-ahead forecast.
5. Returns daily variance, daily volatility, annualized volatility, parameters, fit diagnostics, warnings, and data lineage.

The engine should treat model fitting as a pure domain operation. It should not know about FastAPI, Yahoo, HTTP, or SQLite.

## Storage

V1 uses SQLite because it is auditable, portable, simple to operate, and enough for the initial fixed universe.

### `prices`

One row per provider symbol and date.

| Column | Type | Notes |
| --- | --- | --- |
| provider | text | `yahoo` |
| symbol | text | internal symbol |
| provider_symbol | text | Yahoo symbol |
| date | date | daily bar date |
| open | real | nullable if provider omits |
| high | real | nullable if provider omits |
| low | real | nullable if provider omits |
| close | real | required for modeling fallback |
| adjusted_close | real | preferred for equities when reliable |
| volume | real | nullable |
| fetched_at | timestamp | UTC |
| source_payload_hash | text | nullable hash of normalized provider payload |

Unique key:

```text
provider, provider_symbol, date
```

### `egarch_results`

One row per symbol, window, model spec, and as-of date.

| Column | Type | Notes |
| --- | --- | --- |
| symbol | text | internal symbol |
| provider | text | `yahoo` |
| window | integer | 30, 100, 250, 750 |
| as_of_date | date | last return date |
| model_spec_hash | text | deterministic hash of model config |
| return_type | text | `log_daily_pct` |
| distribution | text | `student_t` |
| variance_daily | real | one-day forecast variance |
| volatility_daily | real | sqrt variance |
| volatility_annualized | real | annualized by asset calendar |
| parameters_json | text | omega, alpha, gamma, beta, nu, mean |
| diagnostics_json | text | aic, bic, loglikelihood, convergence |
| warnings_json | text | controlled warnings |
| created_at | timestamp | UTC |

Unique key:

```text
symbol, window, as_of_date, model_spec_hash
```

### `refresh_runs`

Tracks provider refresh attempts.

| Column | Type | Notes |
| --- | --- | --- |
| id | text | UUID |
| provider | text | `yahoo` |
| symbol | text | internal symbol |
| started_at | timestamp | UTC |
| finished_at | timestamp | UTC nullable |
| status | text | success, failed, partial |
| requested_start | date | fetch start |
| requested_end | date | fetch end |
| rows_upserted | integer | count |
| error_code | text | nullable |
| error_message | text | nullable sanitized |

## Freshness Rules

The service must calculate an `expected_as_of_date` for each request.

### Equities

For Mag 7 equities, use the most recent closed US market day. If the request arrives on Wednesday 2026-06-24, the expected as-of date is Tuesday 2026-06-23, assuming Yahoo has published that close.

V1 should use an exchange-calendar implementation for US equities rather than a simple weekday approximation. The calendar service must be isolated so holiday rules and early-close behavior can be upgraded without changing endpoint contracts.

### Futures

For futures, use the most recent daily bar available from Yahoo up to T-1. Because Yahoo futures data can differ from exchange settlement conventions, the result must expose the final `as_of_date` and provider lineage. If the expected bar is absent after refresh, return `stale_data` unless `allow_stale=true`.

### Crypto

For crypto, use yesterday calendar day because crypto trades every day.

Annualization should use:

- 252 for equities and futures
- 365 for crypto

## Effective Price Selection

The service should determine the modeling price as follows:

- Equities: prefer adjusted close when present and valid; fallback to close.
- Futures: prefer close.
- Crypto: prefer close.

Every result should include the effective price field used.

## API Contracts

### `GET /health`

Response:

```json
{
  "status": "ok",
  "service": "egarch-service",
  "version": "0.1.0",
  "database": "ok"
}
```

### `GET /assets`

Response:

```json
{
  "assets": [
    {
      "symbol": "AAPL",
      "provider": "yahoo",
      "provider_symbol": "AAPL",
      "asset_class": "equity",
      "calendar": "us_equity",
      "supported_windows": [30, 100, 250, 750]
    }
  ]
}
```

### `GET /egarch/{symbol}`

Example:

```http
GET /egarch/AAPL?window=250&allow_stale=false
```

Response:

```json
{
  "symbol": "AAPL",
  "provider": "yahoo",
  "provider_symbol": "AAPL",
  "asset_class": "equity",
  "window": 250,
  "as_of_date": "2026-06-23",
  "model": {
    "type": "EGARCH",
    "order": {"p": 1, "o": 1, "q": 1},
    "distribution": "student_t",
    "mean": "constant",
    "return_type": "log_daily_pct",
    "model_spec_hash": "sha256:egarch-v1-student-t-log-daily-pct"
  },
  "forecast": {
    "horizon_days": 1,
    "variance_daily": 0.00033856,
    "volatility_daily": 0.0184,
    "volatility_annualized": 0.2921
  },
  "parameters": {
    "mu": 0.04,
    "omega": -0.12,
    "alpha": 0.09,
    "gamma": -0.04,
    "beta": 0.94,
    "nu": 8.7
  },
  "diagnostics": {
    "loglikelihood": -340.12,
    "aic": 692.24,
    "bic": 713.31,
    "converged": true,
    "optimizer_status": "success"
  },
  "data": {
    "observations": 250,
    "first_date": "2025-06-24",
    "last_date": "2026-06-23",
    "expected_as_of_date": "2026-06-23",
    "freshness": "fresh",
    "effective_price_field": "adjusted_close"
  },
  "cache": {
    "price_cache_hit": true,
    "result_cache_hit": false
  },
  "warnings": []
}
```

### `POST /egarch/batch`

Request:

```json
{
  "symbols": ["AAPL", "NVDA", "ES", "BTC"],
  "windows": [30, 100, 250, 750],
  "allow_stale": false
}
```

This endpoint requires an administrative API key. Refresh operations should be idempotent and should upsert normalized price rows rather than deleting and rewriting history.

Response:

```json
{
  "results": [],
  "errors": [
    {
      "symbol": "ES",
      "window": 30,
      "error_code": "stale_data",
      "message": "Expected daily bar is not available from provider."
    }
  ]
}
```

Batch requests must isolate failures. One failing asset/window must not block successful results for other pairs.

### `POST /prices/refresh`

Administrative endpoint for forced price refresh.

Request:

```json
{
  "symbols": ["AAPL", "BTC"],
  "start_date": "2020-01-01",
  "end_date": "2026-06-23"
}
```

## Error Policy

| HTTP | Code | Meaning |
| --- | --- | --- |
| 400 | unsupported_symbol | Symbol is not in asset registry |
| 400 | unsupported_window | Window is not one of 30, 100, 250, 750 |
| 409 | stale_data | Cache/provider does not reach expected as-of date |
| 422 | insufficient_history | Not enough prices for requested window |
| 422 | model_failed_to_converge | EGARCH fit did not produce a usable result |
| 503 | provider_unavailable | Yahoo request failed or timed out |
| 500 | internal_error | Unexpected service failure |

Convergence policy:

- If the optimizer clearly fails or produces invalid variance, return `422 model_failed_to_converge`.
- If the optimizer converges but the fit is fragile, return a result with warnings.

Warnings:

- `short_window_model_may_be_unstable` for `window=30`.
- `provider_bar_pending` when Yahoo appears not to have published the expected latest bar.
- `fallback_to_close_used` when adjusted close was expected but unavailable.

Provider resilience:

- Yahoo requests must use bounded timeouts.
- Transient provider failures should retry with exponential backoff and jitter.
- Provider responses should be validated before storage.
- The service should not mutate existing cached rows unless the incoming normalized bar is valid.
- Refresh failures should be recorded in `refresh_runs`.

## Observability

Every request should log structured events with:

- request ID
- endpoint
- symbol
- window
- expected as-of date
- actual as-of date
- cache hit or miss
- provider refresh duration
- EGARCH fit duration
- convergence status
- warning codes
- error code

Logs should be machine-readable JSON. The service should expose enough metadata in responses for downstream systems to decide whether a number is acceptable.

## State-Of-The-Art Product Standards

V1 should be small but not sloppy. The implementation should follow these standards:

- Deterministic model specs, represented by a versioned model config and hash.
- Explicit data lineage for every forecast.
- Strict freshness behavior by default.
- Provider abstraction so Yahoo can later be replaced or supplemented by Polygon, Databento, Tiingo, Alpaca, or an internal data warehouse.
- Separation between domain logic and HTTP framework.
- Repositories for persistence; no SQL hidden in route handlers.
- Pydantic contracts at the API boundary.
- Typed domain models inside the service.
- Partial-failure semantics for batch workloads.
- Convergence diagnostics exposed, not hidden.
- Reproducible test fixtures instead of tests that depend on live Yahoo.
- Live provider smoke tests separated from unit tests.
- Administrative endpoints protected by API key from the first implementation.
- Bounded provider timeouts and retries.
- Clear distinction between deterministic tests and live market-data checks.
- No route handler should fit models directly; model execution belongs in the forecasting service and EGARCH engine.

## Test Strategy

Unit tests:

- asset registry maps internal symbols correctly
- unsupported symbols fail validation
- supported windows validate correctly
- expected as-of date calculation for equities, futures, crypto
- effective price selection
- log-return calculation
- annualization factor selection
- result cache key generation
- stale cache detection
- model warnings for short windows
- batch partial failure behavior

Integration tests:

- SQLite schema creation and upsert behavior
- price refresh into cache using mocked provider data
- EGARCH endpoint using deterministic local fixtures
- batch endpoint with mixed success and failure

Provider smoke tests:

- optional, manually triggered or CI-gated
- verify Yahoo can return recent daily data for representative symbols
- never block deterministic unit test suite by default

Model validation tests:

- confirm forecasts are positive finite numbers
- confirm expected parameter keys are emitted
- confirm non-convergence paths return controlled errors
- compare stable fixture outputs within tolerances

## Implementation Notes

Recommended package structure:

```text
egarch_service/
  api/
    routes.py
    schemas.py
    dependencies.py
  assets/
    registry.py
    calendars.py
  data/
    providers.py
    yahoo.py
    repositories.py
    sqlite.py
  modeling/
    returns.py
    egarch.py
    diagnostics.py
  services/
    freshness.py
    forecasts.py
    refresh.py
  config.py
  main.py
tests/
  unit/
  integration/
  fixtures/
```

Recommended dependencies:

- `fastapi`
- `uvicorn`
- `pydantic`
- `pydantic-settings`
- `pandas`
- `numpy`
- `arch`
- `yfinance`
- `sqlalchemy`
- `httpx`
- `exchange-calendars` or `pandas-market-calendars`
- `pytest`
- `pytest-cov`
- `ruff`
- `mypy` or `pyright`

## References

- `arch` documentation supports univariate volatility modeling, EGARCH-style model configuration, Student-t errors, and one-step-ahead forecasting through result forecast objects.
- FastAPI documentation recommends dependency injection for reusable service dependencies.
- yfinance documentation describes it as an open-source tool over Yahoo's public finance APIs and notes it is intended for research and educational use. The service should keep Yahoo behind a provider interface for this reason.

## Approval

The user approved:

- service architecture
- Yahoo Finance as initial provider
- mixed universe of Mag 7, futures, and crypto
- daily data only
- fixed windows of 30, 100, 250, and 750 days
- one-day-ahead forecast only
- cache prices with mandatory T-1 freshness
- REST individual and batch endpoints
- Python and FastAPI
- EGARCH(1,1), Student-t, log daily returns
- response including annualized volatility, parameters, and diagnostics
- strict error and validation policy

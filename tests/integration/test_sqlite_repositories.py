from dataclasses import replace
from datetime import date

from egarch_service.data import (
    CacheFreshness,
    DailyBar,
    EgarchResultRecord,
    EgarchResultRepository,
    PriceRepository,
    RefreshRunRepository,
    connect_database,
    initialize_schema,
)


def test_sqlite_schema_price_upsert_and_stale_detection() -> None:
    connection = connect_database(":memory:")
    initialize_schema(connection)
    prices = PriceRepository(connection)

    bars = [
        DailyBar(
            provider="yahoo",
            symbol="AAPL",
            provider_symbol="AAPL",
            date=date(2026, 6, 22),
            open=199.0,
            high=203.0,
            low=198.0,
            close=202.0,
            adjusted_close=201.5,
            volume=1_000_000,
            source_payload_hash="sha256:one",
        ),
        DailyBar(
            provider="yahoo",
            symbol="AAPL",
            provider_symbol="AAPL",
            date=date(2026, 6, 23),
            open=202.0,
            high=204.0,
            low=200.0,
            close=203.0,
            adjusted_close=202.5,
            volume=1_100_000,
            source_payload_hash="sha256:two",
        ),
    ]

    assert prices.upsert_daily_bars(bars, fetched_at="2026-06-24T00:00:00+00:00") == 2
    assert prices.upsert_daily_bars(bars, fetched_at="2026-06-24T01:00:00+00:00") == 2

    rows = connection.execute("SELECT COUNT(*) AS count FROM prices").fetchone()
    assert rows["count"] == 2
    assert prices.latest_price_date("yahoo", "AAPL") == date(2026, 6, 23)
    assert prices.has_price_through("yahoo", "AAPL", date(2026, 6, 23)) is True
    assert prices.cache_freshness("yahoo", "AAPL", date(2026, 6, 24)) == CacheFreshness.STALE
    assert prices.cache_freshness("yahoo", "MSFT", date(2026, 6, 23)) == CacheFreshness.EMPTY

    stored = prices.get_daily_bars("yahoo", "AAPL", end_date=date(2026, 6, 22))
    assert len(stored) == 1
    assert stored[0].adjusted_close == 201.5


def test_refresh_run_tracking_success_and_failure_metadata() -> None:
    connection = connect_database(":memory:")
    initialize_schema(connection)
    runs = RefreshRunRepository(connection)

    run = runs.start_run("yahoo", "BTC", date(2026, 6, 1), date(2026, 6, 23))
    finished = runs.finish_run(run.id, "success", rows_upserted=23)

    assert finished.finished_at is not None
    assert finished.status == "success"
    assert finished.rows_upserted == 23
    assert finished.error_code is None

    failed = runs.start_run("yahoo", "ES", date(2026, 6, 1), date(2026, 6, 23))
    finished_failed = runs.finish_run(
        failed.id,
        "failed",
        rows_upserted=0,
        error_code="provider_unavailable",
        error_message="timeout while contacting Yahoo" * 50,
    )

    assert finished_failed.status == "failed"
    assert finished_failed.error_code == "provider_unavailable"
    assert finished_failed.error_message is not None
    assert len(finished_failed.error_message) == 500


def test_egarch_result_upsert_is_idempotent_by_model_cache_key() -> None:
    connection = connect_database(":memory:")
    initialize_schema(connection)
    results = EgarchResultRepository(connection)

    record = EgarchResultRecord(
        symbol="AAPL",
        provider="yahoo",
        window=250,
        as_of_date=date(2026, 6, 23),
        model_spec_hash="sha256:egarch-v1-student-t-log-daily-pct",
        return_type="log_daily_pct",
        distribution="student_t",
        variance_daily=0.0003,
        volatility_daily=0.017,
        volatility_annualized=0.27,
        parameters={"omega": -0.1, "beta": 0.9},
        diagnostics={"aic": 123.4, "converged": True},
        warnings=[],
        created_at="2026-06-24T00:00:00+00:00",
    )

    results.upsert_result(record)
    results.upsert_result(
        replace(
            record,
            variance_daily=0.0004,
            warnings=["short_window_model_may_be_unstable"],
        )
    )

    rows = connection.execute("SELECT COUNT(*) AS count FROM egarch_results").fetchone()
    assert rows["count"] == 1
    stored = results.get_result(
        "AAPL",
        250,
        date(2026, 6, 23),
        "sha256:egarch-v1-student-t-log-daily-pct",
    )
    assert stored is not None
    assert stored.variance_daily == 0.0004
    assert stored.warnings == ["short_window_model_may_be_unstable"]

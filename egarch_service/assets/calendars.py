from __future__ import annotations

from datetime import date, timedelta

import exchange_calendars as xcals

from egarch_service.assets.registry import Asset
from egarch_service.domain import AssetClass

_US_EQUITY_CALENDAR = "XNYS"


def expected_as_of_date(
    asset: Asset | AssetClass | str,
    request_date: date | None = None,
) -> date:
    """Return the strict T-1 expected last daily bar date for an asset."""
    today = request_date or date.today()
    asset_class = asset.asset_class if isinstance(asset, Asset) else AssetClass(asset)
    if asset_class is AssetClass.EQUITY:
        return previous_us_equity_session(today)
    if asset_class in {AssetClass.FUTURE, AssetClass.CRYPTO}:
        return today - timedelta(days=1)
    raise ValueError(f"Unsupported asset class: {asset_class}")


def previous_us_equity_session(request_date: date) -> date:
    """Return the most recent closed XNYS session strictly before request_date."""
    calendar = xcals.get_calendar(_US_EQUITY_CALENDAR)
    cursor = request_date - timedelta(days=1)
    while not bool(calendar.is_session(cursor)):
        cursor -= timedelta(days=1)
    return cursor

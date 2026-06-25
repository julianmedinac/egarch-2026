from __future__ import annotations

from collections.abc import Iterable

from egarch_service.assets.registry import Asset
from egarch_service.domain import DailyBar, EffectivePrice


def select_effective_price(asset: Asset, bar: DailyBar) -> EffectivePrice:
    return asset.effective_price(bar)


def select_effective_prices(asset: Asset, bars: Iterable[DailyBar]) -> list[EffectivePrice]:
    return [select_effective_price(asset, bar) for bar in bars]

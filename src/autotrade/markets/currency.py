"""通貨・為替（FX）— 現地通貨と円換算。

米国株はドル建てのため、評価を「現地通貨建て」と「円換算」の両建てで見られるようにする。
Phase 1 では固定レート（FlatFXRate）を提供。将来はヒストリカル為替に差し替える。
為替手数料は execution の CostModel 側で取引コストとして織り込む。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Currency:
    code: str  # "JPY" / "USD"


class FXRate:
    """為替レートの抽象。base→quote のレートを返す。"""

    def rate(self, base: str, quote: str, date=None) -> float:
        raise NotImplementedError


@dataclass
class FlatFXRate(FXRate):
    """固定レート。例: USDJPY=150 なら ``FlatFXRate(usd_jpy=150.0)``。"""

    usd_jpy: float = 150.0

    def rate(self, base: str, quote: str, date=None) -> float:
        base, quote = base.upper(), quote.upper()
        if base == quote:
            return 1.0
        if base == "USD" and quote == "JPY":
            return self.usd_jpy
        if base == "JPY" and quote == "USD":
            return 1.0 / self.usd_jpy
        raise ValueError(f"未対応の通貨ペアです: {base}->{quote}")

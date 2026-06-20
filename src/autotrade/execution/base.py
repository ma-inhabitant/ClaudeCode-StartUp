"""Broker 抽象・コストモデル・ポートフォリオ。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

from autotrade.types import Fill, Order, Position, Side


@dataclass
class CostModel:
    """取引コスト。★コストゼロのバックテストは禁止（保守的な既定を使う）。

    - commission_rate: 約定代金に対する手数料率
    - min_commission : 1約定あたりの最低手数料（現地通貨）
    - slippage_bps   : 価格に対するスリッページ（ベーシスポイント, 1bp=0.01%）
    - fx_fee_rate    : 為替手数料率（米国株など外貨取引のみ。日本株は0）
    """

    commission_rate: float = 0.0
    min_commission: float = 0.0
    slippage_bps: float = 0.0
    fx_fee_rate: float = 0.0

    def fill_price(self, ref_price: float, side: Side) -> float:
        slip = ref_price * self.slippage_bps / 10_000.0
        # 買いは不利方向（高く）、売りは不利方向（安く）約定する。
        return ref_price + slip if side == Side.BUY else ref_price - slip

    def commission(self, trade_value: float) -> float:
        return max(self.min_commission, trade_value * self.commission_rate)

    def fx_fee(self, trade_value: float) -> float:
        return trade_value * self.fx_fee_rate


@dataclass
class Portfolio:
    """現金とポジションを保持する。通貨は market の現地通貨建て。"""

    cash: float
    currency: str = "JPY"
    positions: Dict[str, Position] = field(default_factory=dict)

    def position(self, symbol: str) -> Position:
        return self.positions.setdefault(symbol, Position(symbol=symbol))

    def equity(self, price_fn: Callable[[str], float]) -> float:
        """時価評価額 = 現金 + 保有ポジションの時価合計。"""
        total = self.cash
        for sym, pos in self.positions.items():
            if pos.is_open:
                total += pos.shares * price_fn(sym)
        return total


class Broker(ABC):
    @abstractmethod
    def execute(self, order: Order, ref_price: float, date) -> Optional[Fill]:
        """注文を ``ref_price`` を基準に約定させ、ポートフォリオを更新する。"""
        raise NotImplementedError

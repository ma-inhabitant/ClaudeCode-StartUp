"""BacktestBroker — 約定シミュレーション。

- スリッページ・手数料・為替手数料を必ず適用する。
- 買付余力（現金）を超える買いは約定させない（部分的に丸める）。
- ポジションのクローズ時に実現損益を記録し、勝率・損益分析に使う。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from autotrade.execution.base import Broker, CostModel, Portfolio
from autotrade.types import Fill, Order, Position, Side


@dataclass
class Trade:
    """クローズした取引（1ポジションの手仕舞い単位）の記録。"""

    symbol: str
    entry_date: object
    exit_date: object
    shares: float
    entry_price: float
    exit_price: float
    pnl: float  # コスト控除後の実現損益（現地通貨）
    reason: str


class BacktestBroker(Broker):
    def __init__(self, portfolio: Portfolio, cost_model: CostModel, lot_size: int = 1):
        self.portfolio = portfolio
        self.cost = cost_model
        self.lot_size = lot_size
        self.fills: List[Fill] = []
        self.trades: List[Trade] = []
        # 実現損益の集計用に、エントリー時の手数料も損益へ反映する。
        self._entry_costs: dict[str, float] = {}

    def execute(self, order: Order, ref_price: float, date) -> Optional[Fill]:
        if order.shares <= 0 or ref_price <= 0 or math.isnan(ref_price):
            return None
        if order.side == Side.BUY:
            return self._buy(order, ref_price, date)
        return self._sell(order, ref_price, date)

    def _buy(self, order: Order, ref_price: float, date) -> Optional[Fill]:
        price = self.cost.fill_price(ref_price, Side.BUY)
        shares = order.shares
        # 買付余力に収まるよう株数を丸める（手数料・為替手数料も考慮）。
        affordable = self._max_affordable_shares(price)
        shares = min(shares, affordable)
        shares = self._round_lot(shares)
        if shares <= 0:
            return None

        value = price * shares
        commission = self.cost.commission(value)
        fx_fee = self.cost.fx_fee(value)
        self.portfolio.cash -= value + commission + fx_fee

        pos = self.portfolio.position(order.symbol)
        if pos.is_open:
            # 既存ポジションへ買い増し: 取得単価を加重平均で更新。
            total_shares = pos.shares + shares
            pos.entry_price = (pos.entry_price * pos.shares + price * shares) / total_shares
            pos.shares = total_shares
        else:
            pos.shares = shares
            pos.entry_price = price
            pos.entry_date = date
        self._entry_costs[order.symbol] = self._entry_costs.get(order.symbol, 0.0) + commission + fx_fee

        fill = Fill(date, order.symbol, Side.BUY, shares, price, commission, fx_fee, order.reason)
        self.fills.append(fill)
        return fill

    def _sell(self, order: Order, ref_price: float, date) -> Optional[Fill]:
        pos = self.portfolio.position(order.symbol)
        if not pos.is_open:
            return None
        price = self.cost.fill_price(ref_price, Side.SELL)
        shares = self._round_lot(min(order.shares, pos.shares))
        if shares <= 0:
            return None

        value = price * shares
        commission = self.cost.commission(value)
        fx_fee = self.cost.fx_fee(value)
        self.portfolio.cash += value - commission - fx_fee

        # 実現損益（コスト控除後）: 売却益 - 売却コスト - 対応するエントリーコスト按分。
        frac = shares / pos.shares
        entry_cost_alloc = self._entry_costs.get(order.symbol, 0.0) * frac
        self._entry_costs[order.symbol] = self._entry_costs.get(order.symbol, 0.0) - entry_cost_alloc
        pnl = (price - pos.entry_price) * shares - commission - fx_fee - entry_cost_alloc

        self.trades.append(
            Trade(
                symbol=order.symbol,
                entry_date=pos.entry_date,
                exit_date=date,
                shares=shares,
                entry_price=pos.entry_price,
                exit_price=price,
                pnl=pnl,
                reason=order.reason,
            )
        )

        pos.shares -= shares
        if pos.shares <= 1e-9:
            # 完全クローズ。
            pos.shares = 0.0
            pos.entry_price = 0.0
            pos.entry_date = None
            pos.stop_price = None
            pos.tp_price = None
            self._entry_costs[order.symbol] = 0.0

        fill = Fill(date, order.symbol, Side.SELL, shares, price, commission, fx_fee, order.reason)
        self.fills.append(fill)
        return fill

    def _max_affordable_shares(self, price: float) -> float:
        # commission/fx を粗く見込んで現金で買える上限株数を求める。
        cash = self.portfolio.cash
        if cash <= 0:
            return 0.0
        per_share_cost = price * (1.0 + self.cost.commission_rate + self.cost.fx_fee_rate)
        if per_share_cost <= 0:
            return 0.0
        # 最低手数料ぶんを差し引いてから割る。
        usable = cash - self.cost.min_commission
        return max(0.0, usable / per_share_cost)

    def _round_lot(self, shares: float) -> float:
        if self.lot_size <= 1:
            return float(int(shares))  # 1株刻み
        return float(int(shares // self.lot_size) * self.lot_size)

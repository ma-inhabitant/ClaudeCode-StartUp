"""RiskManager — サイジング・損切り/利確・最大ドローダウン制限。

責務（戦略から独立）:
  1. 損切り / 利確         … エントリー時に stop/tp を設定し、毎日 high/low で判定。
  2. ポジションサイズ管理   … 1銘柄あたり・全体のエクスポージャ上限。整数株に丸める。
  3. 最大DDブレーカー       … DD が閾値を超えたら新規エントリーを停止。
取引コストは execution(CostModel) 側で常に適用される。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from autotrade.data.base import PriceData
from autotrade.execution.base import Portfolio
from autotrade.types import Fill, Order, Side


@dataclass
class RiskParams:
    stop_loss_pct: float = 0.08          # 損切り: 取得価格から -8%
    take_profit_pct: Optional[float] = 0.20  # 利確: 取得価格から +20%。None/0 で利確オフ
    trailing_stop_pct: Optional[float] = None  # トレーリングストップ: 取得後の最高値から -x%。Noneでオフ
    per_symbol_max_weight: float = 0.20  # 1銘柄あたり最大エクスポージャ（資産比）
    max_gross_exposure: float = 1.00     # ポートフォリオ全体の最大エクスポージャ
    max_drawdown_pct: float = 0.20       # 最大DD: -20% でサーキットブレーカー作動

    # 補足: 利確(take_profit)はモメンタム系の「勝者を伸ばす」戦略と相性が悪い
    # （大化け株を途中で売ってしまう）。その場合は take_profit_pct=None にして
    # trailing_stop_pct で“伸ばしつつ守る”のが定石。


class RiskManager:
    def __init__(self, params: RiskParams):
        self.p = params
        self._peak_equity: float = 0.0
        self.halted: bool = False  # 最大DDブレーカーの状態

    # --- 最大ドローダウン・ブレーカー -------------------------------------
    def update_drawdown(self, equity: float) -> bool:
        """資産曲線を更新し、ブレーカー状態（True=新規停止）を返す。"""
        self._peak_equity = max(self._peak_equity, equity)
        if self._peak_equity <= 0:
            return self.halted
        dd = equity / self._peak_equity - 1.0
        # 浮動小数点誤差で「ちょうど閾値」を取りこぼさないよう微小なイプシロンを足す。
        self.halted = dd <= -self.p.max_drawdown_pct + 1e-12
        return self.halted

    # --- 損切り / 利確 ----------------------------------------------------
    def on_fill(self, fill: Fill, portfolio: Portfolio) -> None:
        """エントリー約定時に stop/tp を設定する。"""
        if fill.side != Side.BUY:
            return
        pos = portfolio.position(fill.symbol)
        if pos.is_open:
            pos.stop_price = pos.entry_price * (1.0 - self.p.stop_loss_pct)
            # 利確は任意（None/0 でオフ）。モメンタム系では外すことが多い。
            if self.p.take_profit_pct:
                pos.tp_price = pos.entry_price * (1.0 + self.p.take_profit_pct)
            else:
                pos.tp_price = None
            pos.high_water = pos.entry_price  # トレーリングの基準を初期化

    def check_stops(self, portfolio: Portfolio, prices: PriceData, date, broker) -> None:
        """当日の high/low で損切り・利確を判定し、ヒットしたら手仕舞う。"""
        for sym, pos in list(portfolio.positions.items()):
            if not pos.is_open or not prices.has_price(sym, date):
                continue
            low = prices.price(sym, date, "low")
            high = prices.price(sym, date, "high")
            open_ = prices.price(sym, date, "open")

            # トレーリングストップ: 取得後の最高値を更新し、そこから -x% に損切り線を引き上げる
            # （下げることはしない＝利益を守りつつ伸ばす）。
            if self.p.trailing_stop_pct:
                pos.high_water = max(pos.high_water, high)
                trail = pos.high_water * (1.0 - self.p.trailing_stop_pct)
                pos.stop_price = max(pos.stop_price or 0.0, trail)

            # 損切りを優先（保守的）。ギャップダウン時は始値で約定。
            if pos.stop_price is not None and low <= pos.stop_price:
                ref = min(open_, pos.stop_price)
                broker.execute(Order(sym, Side.SELL, pos.shares, "stop"), ref, date)
            elif pos.tp_price is not None and high >= pos.tp_price:
                ref = max(open_, pos.tp_price)
                broker.execute(Order(sym, Side.SELL, pos.shares, "take_profit"), ref, date)

    # --- サイジング（シグナル → 発注） ------------------------------------
    def build_orders(
        self,
        signal_row: pd.Series,
        portfolio: Portfolio,
        prices: PriceData,
        date,
        equity: float,
    ) -> List[Order]:
        """目標シグナルから翌営業日の発注リストを作る。"""
        orders: List[Order] = []

        held = {s for s, p in portfolio.positions.items() if p.is_open}
        wanted = {
            s
            for s in signal_row.index
            if signal_row.get(s) == 1 and prices.has_price(s, date)
        }

        # 1) 手仕舞い: 保有しているがシグナルが消えた銘柄を売る。
        for sym in held - wanted:
            pos = portfolio.position(sym)
            orders.append(Order(sym, Side.SELL, pos.shares, "exit"))

        # 2) 新規: ブレーカー作動中は新規エントリーしない。
        if self.halted:
            return orders

        # 全体エクスポージャ上限の範囲で、新規に持てる銘柄数を決める。
        weight = self.p.per_symbol_max_weight
        max_positions = int(self.p.max_gross_exposure / weight) if weight > 0 else 0
        slots = max(0, max_positions - len(held))

        new_symbols = sorted(wanted - held)[:slots]
        for sym in new_symbols:
            ref_price = prices.price(sym, date, "close")  # 当日終値でサイジング（約定は翌始値）
            if ref_price <= 0:
                continue
            target_value = equity * weight
            shares = int(target_value / ref_price)  # 1株刻み（整数）
            if shares >= 1:
                orders.append(Order(sym, Side.BUY, float(shares), "entry"))

        return orders

"""BacktestEngine — 時系列ループでシステム全体を駆動する。

★ルックアヘッドバイアス厳禁の設計:
  - シグナルは「当日終値までの情報」で決定する。
  - その注文は「翌営業日の始値」で約定する（当日の終値では約定しない）。
  - 損切り/利確は当日の high/low で判定する（前日までに置いた逆指値の発動）。

1日のループ順:
  1. 前日の判断で出した発注を当日始値で約定
  2. 当日の high/low で損切り・利確を判定（必要なら手仕舞い）
  3. 当日終値で時価評価し、資産曲線に記録
  4. 最大DDブレーカーを更新
  5. （最終日でなければ）当日終値までの情報で翌日の発注を決定
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from autotrade.backtest.benchmark import buy_and_hold_equity
from autotrade.backtest.metrics import compute_metrics
from autotrade.data.base import PriceData
from autotrade.execution.backtest_broker import BacktestBroker, Trade
from autotrade.execution.base import CostModel, Portfolio
from autotrade.features.builder import FeatureBuilder
from autotrade.markets.calendar import MarketCalendar
from autotrade.risk.manager import RiskManager
from autotrade.strategies.base import Strategy
from autotrade.types import Order


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: List[Trade]
    fills: list
    metrics: Dict[str, float] = field(default_factory=dict)
    benchmark_curve: Optional[pd.Series] = None       # バイ&ホールドの資産曲線
    benchmark_metrics: Dict[str, float] = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        prices: PriceData,
        feature_builder: FeatureBuilder,
        strategy: Strategy,
        risk_manager: RiskManager,
        cost_model: CostModel,
        calendar: MarketCalendar,
        initial_cash: float,
    ):
        self.prices = prices
        self.feature_builder = feature_builder
        self.strategy = strategy
        self.risk = risk_manager
        self.calendar = calendar
        self.cost_model = cost_model
        self.initial_cash = initial_cash
        self.portfolio = Portfolio(cash=initial_cash, currency=calendar.currency)
        self.broker = BacktestBroker(self.portfolio, cost_model, lot_size=calendar.lot_size)

    def run(self) -> BacktestResult:
        prices = self.prices
        dates = prices.dates

        # 特徴量・シグナルは全期間まとめて事前計算（各行は当日までの情報のみ参照=ルックアヘッドなし）。
        features = self.feature_builder.build(prices)
        signals = self.strategy.generate_signals(features)

        equity_records: List[tuple] = []
        pending: List[Order] = []

        for i, date in enumerate(dates):
            # 1. 前日決定の発注を当日始値で約定。
            for order in pending:
                if not prices.has_price(order.symbol, date):
                    continue
                open_price = prices.price(order.symbol, date, "open")
                fill = self.broker.execute(order, open_price, date)
                if fill is not None:
                    self.risk.on_fill(fill, self.portfolio)
            pending = []

            # 2. 当日の high/low で損切り・利確。
            self.risk.check_stops(self.portfolio, prices, date, self.broker)

            # 3. 当日終値で時価評価。
            def close_price(sym: str, _date=date) -> float:
                return prices.price(sym, _date, "close")

            equity = self.portfolio.equity(close_price)
            equity_records.append((date, equity))

            # 4. 最大DDブレーカー更新。
            self.risk.update_drawdown(equity)

            # 5. 翌日の発注を決定（最終日は新規発注しない）。
            if i < len(dates) - 1 and date in signals.index:
                signal_row = signals.loc[date]
                pending = self.risk.build_orders(
                    signal_row, self.portfolio, prices, date, equity
                )

        equity_curve = pd.Series(
            {d: v for d, v in equity_records}, name="equity"
        ).sort_index()
        metrics = compute_metrics(equity_curve, self.broker.trades, self.calendar.currency)

        # バイ&ホールド・ベンチマーク（売買せず持ち続けた場合）を同条件で算出。
        bench_curve = buy_and_hold_equity(self.prices, self.cost_model, self.initial_cash)
        bench_metrics = compute_metrics(bench_curve, [], self.calendar.currency)

        return BacktestResult(
            equity_curve=equity_curve,
            trades=self.broker.trades,
            fills=self.broker.fills,
            metrics=metrics,
            benchmark_curve=bench_curve,
            benchmark_metrics=bench_metrics,
        )

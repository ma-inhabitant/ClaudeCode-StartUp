"""エンジンの結合テスト（合成データでパイプライン全体が動くこと）。"""

import pandas as pd

from autotrade.backtest.engine import BacktestEngine
from autotrade.data.base import PriceData
from autotrade.data.synthetic import SyntheticSource
from autotrade.execution.base import CostModel
from autotrade.features.builder import FeatureBuilder
from autotrade.markets.calendar import get_calendar
from autotrade.risk.manager import RiskManager, RiskParams
from autotrade.strategies.sma_crossover import SMACrossoverStrategy


def _engine(prices, initial_cash=10_000, cost=None):
    return BacktestEngine(
        prices=prices,
        feature_builder=FeatureBuilder(sma_fast=5, sma_slow=20),
        strategy=SMACrossoverStrategy(),
        risk_manager=RiskManager(RiskParams()),
        cost_model=cost or CostModel(commission_rate=0.005, slippage_bps=10),
        calendar=get_calendar("JPX"),
        initial_cash=initial_cash,
    )


def test_backtest_runs_and_is_reproducible():
    src = SyntheticSource(seed=123)
    prices = src.get_prices(["A", "B", "C"], "2021-01-01", "2022-12-31")

    r1 = _engine(prices).run()
    r2 = _engine(prices).run()

    assert len(r1.equity_curve) == len(prices.dates)
    # 同一入力なら結果は完全一致（再現性）。
    pd.testing.assert_series_equal(r1.equity_curve, r2.equity_curve)
    assert "total_return" in r1.metrics
    assert "max_drawdown" in r1.metrics


def test_no_lookahead_first_day_has_no_position():
    src = SyntheticSource(seed=1)
    prices = src.get_prices(["A"], "2021-01-01", "2021-06-30")
    result = _engine(prices).run()
    # 初日は資産＝初期現金（まだ約定していない）。
    assert abs(result.equity_curve.iloc[0] - 10_000) < 1e-9


def test_costs_reduce_returns_vs_no_cost():
    src = SyntheticSource(seed=55)
    prices = src.get_prices(["A", "B"], "2021-01-01", "2022-12-31")

    no_cost = _engine(prices, cost=CostModel()).run()
    with_cost = _engine(
        prices, cost=CostModel(commission_rate=0.01, slippage_bps=30)
    ).run()
    # コストありの最終資産は、コストなし以下になるはず。
    assert with_cost.equity_curve.iloc[-1] <= no_cost.equity_curve.iloc[-1] + 1e-6

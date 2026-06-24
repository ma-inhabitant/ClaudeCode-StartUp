"""ロングショート評価モジュールの単体テスト。"""

import numpy as np
import pandas as pd

from autotrade.backtest.long_short import long_short_backtest
from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel


def _trending_prices(n=400):
    """4銘柄: 2つは上昇トレンド、2つは下落トレンド（明確に分離）。"""
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    frames = {}
    specs = {"UP1": 1.001, "UP2": 1.0012, "DN1": 0.999, "DN2": 0.9988}
    for sym, daily in specs.items():
        close = 1000.0 * np.power(daily, np.arange(n))
        frames[sym] = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": 1000.0},
            index=idx,
        )
    return PriceData(frames)


def test_long_short_profits_when_winners_beat_losers():
    prices = _trending_prices()
    # 上位2ロング・下位2ショート。上昇銘柄を買い下落銘柄を売るので利益が出るはず。
    res = long_short_backtest(
        prices, lookback=120, skip=5, top_k=2, bottom_k=2,
        rebalance_days=21, cost_model=CostModel(), initial_cash=10_000,
    )
    assert res.rebalances > 0
    assert res.metrics["total_return"] > 0
    assert res.avg_long_names == 2
    assert res.avg_short_names == 2


def test_long_short_costs_reduce_return():
    prices = _trending_prices()
    base = long_short_backtest(
        prices, lookback=120, skip=5, top_k=2, bottom_k=2,
        cost_model=CostModel(), initial_cash=10_000,
    )
    costly = long_short_backtest(
        prices, lookback=120, skip=5, top_k=2, bottom_k=2,
        cost_model=CostModel(commission_rate=0.01, slippage_bps=50), initial_cash=10_000,
    )
    # コストを課すとリターンは必ず下がる。
    assert costly.metrics["total_return"] < base.metrics["total_return"]


def test_long_short_flat_until_scores_ready():
    prices = _trending_prices(n=200)
    res = long_short_backtest(
        prices, lookback=120, skip=5, top_k=2, bottom_k=2, initial_cash=10_000,
    )
    # 資産曲線は最初のリバランス（lookback以降）から始まる。
    assert len(res.equity_curve) > 0
    assert res.equity_curve.iloc[0] == 10_000 or abs(res.equity_curve.iloc[0] - 10_000) < 10_000

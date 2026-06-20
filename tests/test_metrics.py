"""指標計算の単体テスト。"""

import numpy as np
import pandas as pd

from autotrade.backtest.metrics import compute_metrics, max_drawdown


def test_max_drawdown_simple():
    eq = pd.Series([100, 120, 90, 130], index=pd.date_range("2021-01-01", periods=4))
    # ピーク120 → 90 で -25%
    assert abs(max_drawdown(eq) - (-0.25)) < 1e-9


def test_total_return_and_final_equity():
    eq = pd.Series([100, 110, 121], index=pd.date_range("2021-01-01", periods=3))
    m = compute_metrics(eq, trades=[])
    assert abs(m["total_return"] - 0.21) < 1e-9
    assert abs(m["final_equity"] - 121) < 1e-9
    assert m["num_trades"] == 0


def test_win_rate_from_trades():
    class T:
        def __init__(self, pnl):
            self.pnl = pnl

    eq = pd.Series([100, 105], index=pd.date_range("2021-01-01", periods=2))
    trades = [T(10), T(-5), T(20), T(-2)]
    m = compute_metrics(eq, trades=trades)
    assert m["num_trades"] == 4
    assert abs(m["win_rate"] - 0.5) < 1e-9
    assert abs(m["profit_factor"] - (30 / 7)) < 1e-9


def test_flat_equity_has_zero_volatility():
    eq = pd.Series([100, 100, 100], index=pd.date_range("2021-01-01", periods=3))
    m = compute_metrics(eq, trades=[])
    assert m["volatility_annual"] == 0.0
    assert np.isnan(m["sharpe"])

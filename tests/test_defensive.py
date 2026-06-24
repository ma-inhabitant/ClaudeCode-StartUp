"""防御的オーバーレイ（インデックス＋暴落回避）の単体テスト。"""

import numpy as np
import pandas as pd

from autotrade.backtest.defensive import defensive_overlay
from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel


def _index_with_crash():
    """上昇 → 大暴落 → 回復、を1銘柄で表現（等金額インデックス＝その銘柄）。"""
    up1 = [100 * 1.01**i for i in range(250)]          # 上昇（移動平均を温める）
    peak = up1[-1]
    crash = [peak * 0.985**i for i in range(120)]       # じわ下げの暴落
    bottom = crash[-1]
    recover = [bottom * 1.012**i for i in range(150)]   # 回復
    closes = up1 + crash + recover
    idx = pd.date_range("2015-01-01", periods=len(closes), freq="B")
    df = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0},
        index=idx,
    )
    return PriceData({"IDX": df})


def test_defensive_reduces_drawdown_in_crash():
    prices = _index_with_crash()
    res = defensive_overlay(prices, trend_days=100, cost_model=CostModel(), initial_cash=10_000)
    # 暴落時に現金へ逃げるので、最大DD（負値）は持ち続けより浅い（大きい＝0に近い）。
    assert res.defensive_metrics["max_drawdown"] > res.buy_hold_metrics["max_drawdown"]
    # 一部の期間は現金回避しているはず（=常時投資ではない）。
    assert res.days_invested_pct < 100.0


def test_defensive_matches_buyhold_when_always_up():
    # ずっと上昇ならレジームは常に上向き → 防御も持ち続けとほぼ同じ（コストなし）。
    closes = [100 * 1.005**i for i in range(400)]
    idx = pd.date_range("2015-01-01", periods=len(closes), freq="B")
    df = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0},
        index=idx,
    )
    res = defensive_overlay(PriceData({"A": df}), trend_days=100, cost_model=CostModel(), initial_cash=10_000)
    diff = abs(res.defensive_metrics["total_return"] - res.buy_hold_metrics["total_return"])
    assert diff < 1e-6

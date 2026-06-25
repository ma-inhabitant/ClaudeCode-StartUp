"""積立支援（お買い物リスト・積立シミュレーション）の単体テスト。"""

import pandas as pd

from autotrade.accumulation import plan_purchases, simulate_accumulation
from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel


def test_plan_respects_budget():
    # 1株1000円・コストなし。予算3500円なら合計3株まで（端数は現金で残す）。
    prices = {"A": 1000.0, "B": 1000.0, "C": 1000.0}
    buys, spent, leftover = plan_purchases(prices, {}, 3500, CostModel())
    assert sum(buys.values()) == 3
    assert spent == 3000.0
    assert leftover == 500.0


def test_plan_diversifies_across_names():
    # 同価格3銘柄・予算3株ぶん → 1株ずつ均等に分散される。
    prices = {"A": 1000.0, "B": 1000.0, "C": 1000.0}
    buys, _, _ = plan_purchases(prices, {}, 3000, CostModel())
    assert buys == {"A": 1, "B": 1, "C": 1}


def test_plan_fills_underweight_first():
    # A を既に多く保有 → 予算は出遅れている B・C に優先的に回る。
    prices = {"A": 1000.0, "B": 1000.0, "C": 1000.0}
    holdings = {"A": 5.0, "B": 0.0, "C": 0.0}
    buys, _, _ = plan_purchases(prices, holdings, 2000, CostModel())
    assert buys.get("A", 0) == 0
    assert buys["B"] == 1 and buys["C"] == 1


def test_plan_buys_nothing_when_too_poor():
    prices = {"A": 5000.0}
    buys, spent, leftover = plan_purchases(prices, {}, 1000, CostModel())
    assert buys == {} and spent == 0.0 and leftover == 1000.0


def _rising_prices(n=300):
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    frames = {}
    for j, sym in enumerate(["A", "B", "C"]):
        close = [(500 + 100 * j) * 1.0008 ** i for i in range(n)]
        frames[sym] = pd.DataFrame(
            {"open": close, "high": close, "low": close, "close": close, "volume": 1.0},
            index=idx,
        )
    return PriceData(frames)


def test_simulate_accumulation_grows_and_tracks_contributions():
    prices = _rising_prices()
    res = simulate_accumulation(prices, initial_cash=50_000, monthly_contribution=10_000, cost_model=CostModel())
    # 月数ぶん投入されている（初回＋各月）。
    assert res.months >= 12
    assert res.total_contributed == 50_000 + 10_000 * (res.months - 1)
    # 価格が上昇トレンドなので最終評価額は投入総額を上回る。
    assert res.final_value > res.total_contributed
    assert res.total_shares_bought > 0
    # 投入額カーブは単調非減少。
    assert (res.contributed_curve.diff().dropna() >= 0).all()

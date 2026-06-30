"""積立支援（お買い物リスト・積立シミュレーション）の単体テスト。"""

import pandas as pd

from autotrade.accumulation import (
    load_holdings,
    plan_purchases,
    simulate_accumulation,
    write_holdings_csv,
    write_plan_csv,
)
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


def test_load_holdings_roundtrip(tmp_path):
    # 書き出し→読み込みで保有が一致する（日本株ティッカーの文字列も保持）。
    path = tmp_path / "holdings.csv"
    write_holdings_csv(str(path), {"7203.T": 3, "9432.T": 10})
    loaded = load_holdings(str(path))
    assert loaded == {"7203.T": 3.0, "9432.T": 10.0}


def test_load_holdings_missing_file_is_empty():
    assert load_holdings("does_not_exist_12345.csv") == {}


def test_load_holdings_japanese_headers(tmp_path):
    # 日本語ヘッダ（銘柄,株数）でも読める。
    path = tmp_path / "h.csv"
    path.write_text("銘柄,株数\n7203.T,2\n6758.T,1\n", encoding="utf-8")
    assert load_holdings(str(path)) == {"7203.T": 2.0, "6758.T": 1.0}


def test_write_plan_csv(tmp_path):
    path = tmp_path / "plan.csv"
    write_plan_csv(str(path), {"A": 2}, {"A": 100.0})
    text = path.read_text(encoding="utf-8-sig")
    assert "symbol,shares,price,est_cost" in text
    assert "A,2,100.00,200" in text


def test_plan_with_existing_holdings_balances_toward_target():
    # A に偏った保有 → 予算は B・C を優先して買い、分散に近づける。
    prices = {"A": 1000.0, "B": 1000.0, "C": 1000.0}
    holdings = load_holdings("none.csv")  # 空
    holdings = {"A": 8.0}
    buys, _, _ = plan_purchases(prices, holdings, 4000, CostModel())
    assert buys.get("A", 0) == 0  # 既に多いので買わない
    assert buys["B"] >= 1 and buys["C"] >= 1


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

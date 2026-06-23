"""バイ&ホールド・ベンチマークの単体テスト。"""

import pandas as pd

from autotrade.backtest.benchmark import buy_and_hold_equity
from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel


def _prices(closes):
    df = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [100] * len(closes)},
        index=pd.date_range("2021-01-01", periods=len(closes)),
    )
    return PriceData({"A": df})


def test_buy_and_hold_tracks_price_without_cost():
    # コストゼロ・1銘柄。100円で買い、最終100→150なら +50%。
    prices = _prices([100.0, 120.0, 150.0])
    eq = buy_and_hold_equity(prices, CostModel(), initial_cash=10_000)
    # 100株買って現金0。最終時価 = 100株 * 150 = 15,000。
    assert eq.iloc[0] == 10_000.0
    assert eq.iloc[-1] == 15_000.0


def test_buy_and_hold_applies_entry_cost():
    # 手数料を入れると初日の評価額は初期資金をわずかに下回る（買った瞬間にコスト分減る）。
    prices = _prices([100.0, 100.0])
    eq = buy_and_hold_equity(prices, CostModel(commission_rate=0.01), initial_cash=10_000)
    assert eq.iloc[0] < 10_000.0


def test_buy_and_hold_rounds_to_whole_shares():
    # 端株は買えない。150円・配分10,000円なら66株（9,900円）で、99円分は現金として残る。
    prices = _prices([150.0, 150.0])
    eq = buy_and_hold_equity(prices, CostModel(), initial_cash=10_000)
    assert eq.iloc[0] == 10_000.0  # 66株*150 + 現金100 = 10,000

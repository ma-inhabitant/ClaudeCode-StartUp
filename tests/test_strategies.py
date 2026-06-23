"""戦略（シグナル生成）の単体テスト。"""

import pandas as pd

from autotrade.strategies.sma_crossover import SMACrossoverStrategy
from autotrade.strategies.trend_filter import TrendFilterStrategy


def _features(rows):
    """1銘柄ぶんの特徴量 DataFrame を組み立てる。各行 = (close, sma_fast, sma_slow, sma_trend, rsi)。"""
    idx = pd.date_range("2021-01-01", periods=len(rows))
    df = pd.DataFrame(
        rows, columns=["close", "sma_fast", "sma_slow", "sma_trend", "rsi"], index=idx
    )
    return {"A": df}


def test_trend_filter_requires_both_short_and_long_uptrend():
    # 行ごとの状況:
    #  0: 短期↑ かつ 全体↑(close>trend) → 買う(1)
    #  1: 短期↑ だが 全体↓(close<trend) → 買わない(0)  ← ここが従来戦略との違い
    #  2: 短期↓ かつ 全体↑               → 買わない(0)
    feat = _features(
        [
            (110, 105, 100, 100, 50),
            (95, 105, 100, 100, 50),
            (110, 95, 100, 100, 50),
        ]
    )
    sig = TrendFilterStrategy().generate_signals(feat)["A"]
    assert list(sig) == [1.0, 0.0, 0.0]


def test_trend_filter_blocks_more_than_sma_crossover_in_downtrend():
    # 短期は一貫して上向き(sma_fast>sma_slow)だが、相場全体は下向き(close<sma_trend)。
    # 従来のクロス戦略は買い続けるが、trend_filter は全期間フラットになる。
    feat = _features([(90, 105, 100, 100, 50)] * 3)
    cross = SMACrossoverStrategy().generate_signals(feat)["A"]
    trend = TrendFilterStrategy().generate_signals(feat)["A"]
    assert list(cross) == [1.0, 1.0, 1.0]
    assert list(trend) == [0.0, 0.0, 0.0]


def test_trend_filter_rsi_guard_blocks_overbought():
    # close>trend かつ 短期↑ でも、rsi_max=70 指定時は RSI>=70 なら買わない。
    feat = _features([(110, 105, 100, 100, 80)])  # RSI=80（買われすぎ）
    on = TrendFilterStrategy(rsi_max=70).generate_signals(feat)["A"]
    off = TrendFilterStrategy().generate_signals(feat)["A"]
    assert list(on) == [0.0]
    assert list(off) == [1.0]


def test_features_not_ready_are_flat_not_long():
    # sma_trend が NaN（未確定）の期間はフラット扱い（買わない）。
    feat = _features([(110, 105, 100, float("nan"), 50)])
    sig = TrendFilterStrategy().generate_signals(feat)["A"]
    assert sig.isna().all()

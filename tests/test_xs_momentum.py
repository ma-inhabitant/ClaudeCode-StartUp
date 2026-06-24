"""横断モメンタム戦略（クロスセクショナル・ランキング）の単体テスト。"""

import numpy as np
import pandas as pd

from autotrade.strategies.xs_momentum import CrossSectionalMomentumStrategy


def _feat_from_close(close_by_sym):
    """終値だけから最小限の特徴量 dict を作る（戦略は close しか使わない）。"""
    n = len(next(iter(close_by_sym.values())))
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    return {
        sym: pd.DataFrame({"close": closes}, index=idx)
        for sym, closes in close_by_sym.items()
    }


def test_top_k_selects_strongest_momentum():
    # lookback=3, skip=1。スコア = close.shift(1)/close.shift(3) - 1。
    # 4銘柄を一定比率で増減させ、勢いの強い上位2銘柄が選ばれることを確認。
    n = 6
    feat = _feat_from_close(
        {
            "UP_FAST": [100 * 1.05**i for i in range(n)],   # 最も強い上昇
            "UP_SLOW": [100 * 1.02**i for i in range(n)],   # 緩い上昇
            "FLAT": [100.0] * n,                             # 横ばい
            "DOWN": [100 * 0.97**i for i in range(n)],       # 下落
        }
    )
    sig = CrossSectionalMomentumStrategy(lookback=3, skip=1, top_k=2).generate_signals(feat)
    last = sig.iloc[-1]
    assert last["UP_FAST"] == 1.0
    assert last["UP_SLOW"] == 1.0
    assert last["FLAT"] == 0.0
    assert last["DOWN"] == 0.0


def test_exactly_top_k_longs_per_day():
    n = 10
    feat = _feat_from_close(
        {f"S{j}": [100 * (1 + 0.01 * j) ** i for i in range(n)] for j in range(5)}
    )
    sig = CrossSectionalMomentumStrategy(lookback=3, skip=1, top_k=3).generate_signals(feat)
    # スコアが出そろった行では、ちょうど top_k 銘柄がロング。
    ready = sig.iloc[4:]
    assert (ready.sum(axis=1) == 3).all()


def test_insufficient_history_is_flat():
    feat = _feat_from_close({"A": [100, 101, 102], "B": [100, 99, 98]})
    sig = CrossSectionalMomentumStrategy(lookback=120, skip=20, top_k=1).generate_signals(feat)
    # 履歴不足ではスコアが NaN → 誰もロングしない（全0）。
    assert (sig.to_numpy() == 0.0).all()

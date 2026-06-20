"""移動平均クロス戦略（ベースライン）。

短期 SMA > 長期 SMA のときロング（1）、それ以外はフラット（0）。
シンプルで検証しやすい基準線。ML 戦略を入れる前の比較対象に使う。

★ルックアヘッドなし: その日の sma_fast / sma_slow（当日終値までで算出）だけで判断する。
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from autotrade.strategies.base import Strategy


class SMACrossoverStrategy(Strategy):
    name = "sma_crossover"

    def generate_signals(self, features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        signals = {}
        for sym, feat in features.items():
            sig = (feat["sma_fast"] > feat["sma_slow"]).astype("float")
            # 特徴量が未確定（NaN）の期間はフラット扱い。
            sig = sig.where(feat["sma_fast"].notna() & feat["sma_slow"].notna(), other=pd.NA)
            signals[sym] = sig
        return pd.DataFrame(signals)

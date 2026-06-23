"""トレンドフィルター戦略（移動平均クロスの改良版）。

移動平均クロス（短期 > 長期）に「相場全体も上向きか」の確認を足したもの。
下げ相場で買い続けて損を広げるのを防ぐのが狙い。

買う条件（すべて満たすときだけロング=1。それ以外はフラット=0）:
  1. 短期トレンドが上    … sma_fast > sma_slow（従来の移動平均クロスと同じ）
  2. 相場全体も上向き    … close > sma_trend（例: 200日移動平均線より株価が上）
  （任意）3. 買われすぎでない … rsi < rsi_max（rsi_max を指定したときだけ有効。高値づかみ回避）

「2」がこの戦略の肝。長期トレンドが下向き(下げ相場)のときは新規に買わないので、
2022年のような下落局面での損失を抑えられる。

★ルックアヘッドなし: すべて「当日終値までで算出できる指標」だけで判断する。
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from autotrade.strategies.base import Strategy


class TrendFilterStrategy(Strategy):
    name = "trend_filter"

    def __init__(self, rsi_max: Optional[float] = None):
        # rsi_max … 指定すると「RSI がこの値以上(買われすぎ)なら買わない」フィルターが有効化。
        #           None（既定）なら RSI フィルターは使わない。
        self.rsi_max = rsi_max

    def generate_signals(self, features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        signals = {}
        for sym, feat in features.items():
            uptrend_short = feat["sma_fast"] > feat["sma_slow"]   # 短期トレンドが上
            uptrend_long = feat["close"] > feat["sma_trend"]       # 相場全体も上向き
            long_cond = uptrend_short & uptrend_long

            ready = (
                feat["sma_fast"].notna()
                & feat["sma_slow"].notna()
                & feat["sma_trend"].notna()
            )

            if self.rsi_max is not None:
                long_cond = long_cond & (feat["rsi"] < self.rsi_max)
                ready = ready & feat["rsi"].notna()

            sig = long_cond.astype("float")
            # 指標が未確定（NaN）の期間はフラット扱い（=判断材料がそろうまで買わない）。
            sig = sig.where(ready, other=pd.NA)
            signals[sym] = sig
        return pd.DataFrame(signals)

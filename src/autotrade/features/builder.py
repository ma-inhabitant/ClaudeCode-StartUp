"""FeatureBuilder — 価格 → 特徴量。

★ルックアヘッドバイアス厳禁。
各特徴量は「その日の終値までに入手可能な情報」だけで計算する（過去方向の窓のみ）。
shift や未来参照を行わないこと。出力は銘柄ごとの DataFrame（index=日付）。
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from autotrade.data.base import PriceData


class FeatureBuilder:
    def __init__(
        self,
        sma_fast: int = 20,
        sma_slow: int = 50,
        sma_trend: int = 200,
        rsi_period: int = 14,
        atr_period: int = 14,
    ):
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        # sma_trend … 長期トレンド（相場全体の向き）を見るための長い移動平均。
        # 例: 200 なら「200日移動平均線」。株価がこれより上なら全体が上昇基調。
        self.sma_trend = sma_trend
        self.rsi_period = rsi_period
        self.atr_period = atr_period

    def build(self, prices: PriceData) -> Dict[str, pd.DataFrame]:
        out: Dict[str, pd.DataFrame] = {}
        for sym in prices.symbols:
            df = prices.frame(sym)
            close = df["close"]
            feat = pd.DataFrame(index=df.index)
            feat["close"] = close
            feat["ret1"] = close.pct_change()
            feat["sma_fast"] = close.rolling(self.sma_fast).mean()
            feat["sma_slow"] = close.rolling(self.sma_slow).mean()
            feat["sma_trend"] = close.rolling(self.sma_trend).mean()
            feat["rsi"] = self._rsi(close, self.rsi_period)
            feat["atr"] = self._atr(df, self.atr_period)
            out[sym] = feat
        return out

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        # ゼロ除算は np.nan に（pd.NA だと float 変換で詰まるため np.nan を使う）。
        rs = avg_gain / avg_loss.replace(0.0, np.nan)
        return 100.0 - (100.0 / (1.0 + rs))

    @staticmethod
    def _atr(df: pd.DataFrame, period: int) -> pd.Series:
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        tr = pd.concat(
            [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
            axis=1,
        ).max(axis=1)
        return tr.rolling(period).mean()

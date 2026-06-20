"""合成データソース — ネットワーク不要・再現可能。

パイプライン全体（特徴量→戦略→リスク→約定→評価）を外部依存なしで動かし、
テストやデモに使う。乱数シードを固定して再現性を担保する。
実データではない点に注意（戦略の良し悪しの判断には使えない）。
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

from autotrade.data.base import DataSource, PriceData


class SyntheticSource(DataSource):
    def __init__(self, seed: int = 42, annual_drift: float = 0.05, annual_vol: float = 0.25):
        self.seed = seed
        self.annual_drift = annual_drift
        self.annual_vol = annual_vol

    def get_prices(self, symbols: List[str], start: str, end: str) -> PriceData:
        dates = pd.bdate_range(start=start, end=end)
        if len(dates) == 0:
            raise ValueError("期間に営業日がありません。start/end を確認してください。")

        rng = np.random.default_rng(self.seed)
        dt = 1.0 / 252.0
        mu, sigma = self.annual_drift, self.annual_vol

        frames = {}
        for i, sym in enumerate(symbols):
            # 銘柄ごとに初期値とシードをずらして、相関しない値動きを作る。
            sub_rng = np.random.default_rng(self.seed + i * 1000 + 1)
            n = len(dates)
            shocks = sub_rng.normal(
                (mu - 0.5 * sigma**2) * dt, sigma * np.sqrt(dt), size=n
            )
            start_price = 1000.0 + 500.0 * i
            close = start_price * np.exp(np.cumsum(shocks))

            # OHLC を終値まわりにノイズを乗せて生成（high>=low を保証）。
            intraday = np.abs(sub_rng.normal(0, sigma * np.sqrt(dt), size=n)) * close
            open_ = np.empty(n)
            open_[0] = close[0]
            open_[1:] = close[:-1]  # 翌日始値≈前日終値
            high = np.maximum(open_, close) + intraday
            low = np.minimum(open_, close) - intraday
            low = np.maximum(low, 0.01)
            volume = sub_rng.integers(100_000, 1_000_000, size=n).astype(float)

            frames[sym] = pd.DataFrame(
                {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
                index=dates,
            )
        return PriceData(frames)

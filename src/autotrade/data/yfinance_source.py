"""yfinance データソース — 実データ取得（ネットワーク必要、yfinance 任意依存）。

日本株は ``7203.T`` のように ``.T`` サフィックスを付ける。米国株は ``AAPL`` 等。
本格運用では日本=J-Quants、米国=IBKR/専用API に差し替える前提のプロトタイプ用。
"""

from __future__ import annotations

from typing import List

import pandas as pd

from autotrade.data.base import DataSource, PriceData


class YFinanceSource(DataSource):
    def __init__(self, auto_adjust: bool = True):
        self.auto_adjust = auto_adjust

    def get_prices(self, symbols: List[str], start: str, end: str) -> PriceData:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover - 任意依存
            raise ImportError(
                "yfinance が必要です。`pip install yfinance` でインストールしてください。"
            ) from exc

        frames = {}
        for sym in symbols:
            raw = yf.download(
                sym, start=start, end=end, auto_adjust=self.auto_adjust, progress=False
            )
            if raw is None or raw.empty:
                raise ValueError(f"{sym}: yfinance からデータを取得できませんでした。")
            # yfinance は MultiIndex 列を返すことがあるので平坦化する。
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.rename(columns=str.lower)
            frames[sym] = raw[["open", "high", "low", "close", "volume"]]
        return PriceData(frames)

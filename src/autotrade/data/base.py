"""DataSource 抽象基底と価格データのコンテナ。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

import pandas as pd

# 各銘柄の価格 DataFrame が必ず持つべき列（小文字）。
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class PriceData:
    """銘柄ごとの OHLCV をまとめて保持する。

    内部表現は ``{symbol: DataFrame}``。各 DataFrame は DatetimeIndex（昇順）を持ち、
    列は OHLCV_COLUMNS。全銘柄を営業日の和集合に整列し、欠損は前方補完する。
    """

    def __init__(self, frames: Dict[str, pd.DataFrame]):
        if not frames:
            raise ValueError("PriceData には最低1銘柄の価格データが必要です。")
        self._frames = {sym: self._normalize(df) for sym, df in frames.items()}
        self._align()

    @staticmethod
    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df.columns = [str(c).lower() for c in df.columns]
        missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"価格データに必要な列がありません: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        return df[OHLCV_COLUMNS].sort_index()

    def _align(self) -> None:
        # 全銘柄の日付の和集合に整列。上場前は NaN のまま（取引不可として扱う）。
        all_dates = sorted(set().union(*[df.index for df in self._frames.values()]))
        self._dates: List[pd.Timestamp] = [pd.Timestamp(d) for d in all_dates]
        idx = pd.DatetimeIndex(self._dates)
        for sym, df in self._frames.items():
            # 価格は前方補完（非取引日を埋める）。出来高は 0 埋め。
            re = df.reindex(idx)
            re[["open", "high", "low", "close"]] = re[["open", "high", "low", "close"]].ffill()
            re["volume"] = re["volume"].fillna(0.0)
            self._frames[sym] = re

    @property
    def symbols(self) -> List[str]:
        return list(self._frames.keys())

    @property
    def dates(self) -> List[pd.Timestamp]:
        return list(self._dates)

    def frame(self, symbol: str) -> pd.DataFrame:
        return self._frames[symbol]

    def price(self, symbol: str, date, field: str = "close") -> float:
        """指定日の価格。未上場（NaN）なら NaN を返す。"""
        return float(self._frames[symbol].at[pd.Timestamp(date), field])

    def has_price(self, symbol: str, date) -> bool:
        val = self._frames[symbol].at[pd.Timestamp(date), "close"]
        return pd.notna(val)


class DataSource(ABC):
    """価格データ取得の抽象 IF。市場別実装を差し替え可能にする。"""

    @abstractmethod
    def get_prices(self, symbols: List[str], start: str, end: str) -> PriceData:
        """``symbols`` の ``[start, end]`` 期間の日足を取得して PriceData で返す。"""
        raise NotImplementedError

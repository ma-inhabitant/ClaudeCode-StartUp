"""CSV データソース — 手元に用意した日足 CSV を読み込む。

想定フォーマット（1銘柄=1ファイル、ファイル名が銘柄コード）:
    <dir>/<symbol>.csv
    date,open,high,low,close,volume
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from autotrade.data.base import DataSource, PriceData


class CSVSource(DataSource):
    def __init__(self, directory: str):
        self.directory = Path(directory)

    def get_prices(self, symbols: List[str], start: str, end: str) -> PriceData:
        frames = {}
        for sym in symbols:
            path = self.directory / f"{sym}.csv"
            if not path.exists():
                raise FileNotFoundError(f"CSV が見つかりません: {path}")
            df = pd.read_csv(path, parse_dates=["date"]).set_index("date")
            df = df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
            if df.empty:
                raise ValueError(f"{sym}: 指定期間にデータがありません。")
            frames[sym] = df
        return PriceData(frames)

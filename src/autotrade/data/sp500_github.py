"""GitHub ホストの実 S&P500 日足データソース（ネットワーク許可リスト環境向け）。

yfinance（Yahoo Finance）への egress が許可リストで塞がれている環境でも、
``raw.githubusercontent.com`` 経由なら実在の米国株ヒストリカル OHLCV を取得できる。
データ元は plotly/datasets の ``all_stocks_5yr.csv``（S&P500 構成銘柄の日足、
2013-02-08〜2018-02-07、約505銘柄・実データ）。

一度ダウンロードしたバンドルは ``cache_dir`` にキャッシュし、以降はオフラインで再利用する。
本格運用では日本=J-Quants、米国=IBKR/専用API に差し替える前提のプロトタイプ用。
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import List, Optional

import pandas as pd

from autotrade.data.base import DataSource, PriceData

# plotly/datasets の S&P500 日足バンドル（date,open,high,low,close,volume,Name）。
DEFAULT_URL = (
    "https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv"
)


class SP500GithubSource(DataSource):
    """raw.githubusercontent.com から実 S&P500 日足を取得する DataSource。"""

    def __init__(
        self,
        cache_dir: str = "data/cache",
        url: str = DEFAULT_URL,
        timeout: int = 60,
    ):
        self.cache_dir = Path(cache_dir)
        self.url = url
        self.timeout = timeout

    def _bundle_path(self) -> Path:
        return self.cache_dir / "all_stocks_5yr.csv"

    def _load_bundle(self) -> pd.DataFrame:
        path = self._bundle_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # urllib（標準ライブラリ）でダウンロード。追加依存なし。
            with urllib.request.urlopen(self.url, timeout=self.timeout) as resp:
                path.write_bytes(resp.read())
        return pd.read_csv(path, parse_dates=["date"])

    def get_prices(
        self, symbols: List[str], start: Optional[str], end: Optional[str]
    ) -> PriceData:
        bundle = self._load_bundle()
        frames = {}
        for sym in symbols:
            sub = bundle[bundle["Name"] == sym]
            if sub.empty:
                raise ValueError(
                    f"{sym}: S&P500 バンドルに該当銘柄がありません"
                    f"（収録は実在の S&P500 構成銘柄のみ）。"
                )
            sub = sub.set_index("date")[["open", "high", "low", "close", "volume"]]
            if start is not None:
                sub = sub.loc[sub.index >= pd.Timestamp(start)]
            if end is not None:
                sub = sub.loc[sub.index <= pd.Timestamp(end)]
            if sub.empty:
                raise ValueError(f"{sym}: 指定期間にデータがありません。")
            frames[sym] = sub.sort_index()
        return PriceData(frames)

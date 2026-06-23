"""GitHub ホストの実 S&P500 日足データソース（ネットワーク許可リスト環境向け）。

yfinance（Yahoo Finance）への egress が許可リストで塞がれている環境でも、
``raw.githubusercontent.com`` 経由なら実在の米国株ヒストリカル OHLCV を取得できる。
データ元は plotly/datasets の ``all_stocks_5yr.csv``（S&P500 構成銘柄の日足、
2013-02-08〜2018-02-07、約505銘柄・実データ）。

一度ダウンロードしたバンドルは ``cache_dir`` にキャッシュし、以降はオフラインで再利用する。
本格運用では日本=J-Quants、米国=IBKR/専用API に差し替える前提のプロトタイプ用。
"""

from __future__ import annotations

import http.client
import urllib.error
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
        max_retries: int = 12,
    ):
        self.cache_dir = Path(cache_dir)
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries

    def _bundle_path(self) -> Path:
        return self.cache_dir / "all_stocks_5yr.csv"

    def _download_resumable(self, dest: Path) -> None:
        """Range リクエストで分割ダウンロードし、途中で切れても再開する。

        約29MB のファイルをプロキシ経由で一括取得すると ``IncompleteRead`` で
        切れることがあるため、64KB ずつストリーム書き込みし、切断時は現在の
        バイト位置から ``Range`` で続きを取得する。GitHub raw は 206 に対応。
        """
        tmp = dest.with_name(dest.name + ".part")
        total: Optional[int] = None
        last_err: Optional[Exception] = None

        for _ in range(self.max_retries):
            have = tmp.stat().st_size if tmp.exists() else 0
            req = urllib.request.Request(self.url)
            if have:
                req.add_header("Range", f"bytes={have}-")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    # サーバが Range 非対応で全体(200)を返したら最初から書き直す。
                    if have and getattr(resp, "status", 200) == 200:
                        have = 0
                    if total is None:
                        cr = resp.headers.get("Content-Range")
                        if cr and "/" in cr:
                            total = int(cr.rsplit("/", 1)[-1])
                        else:
                            cl = resp.headers.get("Content-Length")
                            total = (int(cl) + have) if cl is not None else None
                    mode = "ab" if have else "wb"
                    with open(tmp, mode) as f:
                        while True:
                            chunk = resp.read(1 << 16)
                            if not chunk:
                                break
                            f.write(chunk)
            except (http.client.IncompleteRead, urllib.error.URLError, ConnectionError, TimeoutError) as exc:
                # 途中まで書けた分は tmp に残るので、次ループで続きから再取得する。
                last_err = exc
                # IncompleteRead は読めた partial を保持しているので書き足す。
                partial = getattr(exc, "partial", None)
                if partial:
                    with open(tmp, "ab") as f:
                        f.write(partial)
                continue

            if total is None or tmp.stat().st_size >= total:
                tmp.replace(dest)
                return

        raise RuntimeError(
            f"バンドルのダウンロードが完了しませんでした（{tmp.stat().st_size if tmp.exists() else 0}"
            f"/{total} bytes）。最後のエラー: {last_err}"
        )

    def _load_bundle(self) -> pd.DataFrame:
        path = self._bundle_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._download_resumable(path)
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

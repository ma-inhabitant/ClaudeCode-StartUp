"""SP500GithubSource のテスト（キャッシュ利用でネット不要）。"""

import pandas as pd
import pytest

from autotrade.data.sp500_github import SP500GithubSource


def _write_bundle(cache_dir):
    """plotly/datasets と同形式の小さな実データ風バンドルを用意する。"""
    dates = pd.bdate_range("2014-01-01", periods=5)
    rows = []
    for name, base in [("AAPL", 100.0), ("MSFT", 40.0)]:
        for i, d in enumerate(dates):
            px = base + i
            rows.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "open": px,
                    "high": px + 1,
                    "low": px - 1,
                    "close": px + 0.5,
                    "volume": 1_000_000 + i,
                    "Name": name,
                }
            )
    df = pd.DataFrame(rows)
    path = cache_dir / "all_stocks_5yr.csv"
    df.to_csv(path, index=False)


def test_reads_cached_bundle_without_network(tmp_path):
    _write_bundle(tmp_path)
    src = SP500GithubSource(cache_dir=str(tmp_path))
    prices = src.get_prices(["AAPL", "MSFT"], "2014-01-01", "2014-12-31")

    assert set(prices.symbols) == {"AAPL", "MSFT"}
    frame = prices.frame("AAPL")
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(prices.dates) == 5


def test_period_filtering(tmp_path):
    _write_bundle(tmp_path)
    src = SP500GithubSource(cache_dir=str(tmp_path))
    prices = src.get_prices(["AAPL"], "2014-01-03", "2014-01-06")
    # 2014-01-01〜01-07 の営業日のうち、03〜06 に収まる分のみ。
    assert all(pd.Timestamp("2014-01-03") <= d <= pd.Timestamp("2014-01-06")
               for d in prices.dates)


def test_unknown_symbol_raises(tmp_path):
    _write_bundle(tmp_path)
    src = SP500GithubSource(cache_dir=str(tmp_path))
    with pytest.raises(ValueError, match="該当銘柄がありません"):
        src.get_prices(["NOTREAL"], "2014-01-01", "2014-12-31")

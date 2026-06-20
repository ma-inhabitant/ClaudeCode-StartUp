"""Data 層 — DataSource 抽象化。

市場別の実装（合成 / CSV / yfinance / 将来 J-Quants・IBKR）を同一 IF で扱う。
"""

from autotrade.data.base import DataSource, PriceData
from autotrade.data.synthetic import SyntheticSource
from autotrade.data.csv_source import CSVSource

__all__ = ["DataSource", "PriceData", "SyntheticSource", "CSVSource"]

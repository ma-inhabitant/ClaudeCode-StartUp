"""Backtest 層 — 時系列ループ駆動（BacktestEngine）と評価（Metrics）。"""

from autotrade.backtest.engine import BacktestEngine, BacktestResult
from autotrade.backtest.metrics import compute_metrics

__all__ = ["BacktestEngine", "BacktestResult", "compute_metrics"]

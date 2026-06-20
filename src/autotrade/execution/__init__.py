"""Execution 層 — Broker 抽象化と約定シミュレーション。

Phase 1 は BacktestBroker のみ。Paper/Manual(日本・半自動)/IBKR(米国・全自動) は
同一 IF で後から追加する。Phase 1 では実発注コードを書かない（安全第一）。
"""

from autotrade.execution.base import Broker, CostModel, Portfolio
from autotrade.execution.backtest_broker import BacktestBroker

__all__ = ["Broker", "CostModel", "Portfolio", "BacktestBroker"]

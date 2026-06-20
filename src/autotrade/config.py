"""設定ファイル（YAML）の読み込みとオブジェクト組み立て。

config/jp.yaml・config/us.yaml を読み、バックテストに必要な各層を構築する。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from autotrade.backtest.engine import BacktestEngine
from autotrade.data.base import DataSource
from autotrade.data.csv_source import CSVSource
from autotrade.data.synthetic import SyntheticSource
from autotrade.execution.base import CostModel
from autotrade.features.builder import FeatureBuilder
from autotrade.markets.calendar import get_calendar
from autotrade.risk.manager import RiskManager, RiskParams
from autotrade.strategies.sma_crossover import SMACrossoverStrategy

STRATEGIES = {"sma_crossover": SMACrossoverStrategy}


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        raise ValueError(f"設定ファイルの形式が不正です: {path}")
    return cfg


def _build_data_source(data_cfg: Dict[str, Any]) -> DataSource:
    source = (data_cfg or {}).get("source", "synthetic")
    if source == "synthetic":
        opts = data_cfg.get("synthetic", {}) or {}
        return SyntheticSource(**opts)
    if source == "csv":
        opts = data_cfg.get("csv", {}) or {}
        return CSVSource(directory=opts.get("directory", "data"))
    if source == "yfinance":
        from autotrade.data.yfinance_source import YFinanceSource

        opts = data_cfg.get("yfinance", {}) or {}
        return YFinanceSource(**opts)
    raise ValueError(f"未知のデータソース: {source}")


def build_engine(cfg: Dict[str, Any]) -> BacktestEngine:
    calendar = get_calendar(cfg.get("market", "JPX"))

    source = _build_data_source(cfg.get("data", {}))
    universe = cfg["universe"]
    period = cfg.get("period", {})
    prices = source.get_prices(universe, period.get("start"), period.get("end"))

    feat_cfg = cfg.get("features", {}) or {}
    feature_builder = FeatureBuilder(**feat_cfg)

    strat_cfg = cfg.get("strategy", {}) or {}
    strat_name = strat_cfg.get("name", "sma_crossover")
    if strat_name not in STRATEGIES:
        raise ValueError(f"未知の戦略: {strat_name}（対応: {list(STRATEGIES)}）")
    strategy = STRATEGIES[strat_name]()

    risk = RiskManager(RiskParams(**(cfg.get("risk", {}) or {})))
    cost = CostModel(**(cfg.get("cost", {}) or {}))

    return BacktestEngine(
        prices=prices,
        feature_builder=feature_builder,
        strategy=strategy,
        risk_manager=risk,
        cost_model=cost,
        calendar=calendar,
        initial_cash=float(cfg.get("initial_cash", 10_000)),
    )

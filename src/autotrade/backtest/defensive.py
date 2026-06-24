"""防御的オーバーレイ（インデックス＋暴落回避）の評価モジュール。

発想（方向B）: 「持ち続け(インデックス)に勝つ」のは難しいと分かったので、勝つのは
やめて“大コケ”を避ける。普段は等金額インデックスを持ち、相場全体が下向きのときだけ
現金に逃げる。リターンは多少譲っても、最大ドローダウン（暴落時の下げ幅）を抑え、
初心者が途中で投げ出さずに続けられることを狙う。

比較の公平性のため、持ち続けと“同じ等金額インデックスのリターン”を使い、唯一の違いを
「相場が下向きの日は投資せず現金（リターン0）」だけにする。これで「降りる判断」が
本当に下げ幅を減らせるか（&リターンをどれだけ譲るか）を切り分けて検証できる。

相場の向き（レジーム）の判定:
  - 等金額インデックスの水準が、その長期移動平均（既定200日）より上なら「上向き」。
  - ★ルックアヘッドなし: 前日終値までで判定し、投資有無は翌日に適用する。

現金⇄投資を切り替える日には、全建玉を売買するとみなしターンオーバーにコストを課す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

import numpy as np
import pandas as pd

from autotrade.backtest.metrics import compute_metrics
from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel


@dataclass
class DefensiveResult:
    defensive_curve: pd.Series
    buy_hold_curve: pd.Series
    defensive_metrics: Dict[str, float] = field(default_factory=dict)
    buy_hold_metrics: Dict[str, float] = field(default_factory=dict)
    days_invested_pct: float = 0.0   # 投資していた日の割合（残りは現金回避）


def _equal_weight_index_returns(prices: PriceData) -> pd.Series:
    """全銘柄を等金額で持つインデックスの日次リターン（毎日リバランス相当）。"""
    closes = pd.DataFrame({sym: prices.frame(sym)["close"] for sym in prices.symbols})
    rets = closes.pct_change()
    # その日に値がある銘柄だけの平均（上場前/欠損は除外）。
    return rets.mean(axis=1, skipna=True).fillna(0.0)


def defensive_overlay(
    prices: PriceData,
    trend_days: int = 200,
    cost_model: CostModel | None = None,
    initial_cash: float = 10_000.0,
    currency: str = "JPY",
) -> DefensiveResult:
    cost = cost_model or CostModel()
    cost_rate = cost.commission_rate + cost.slippage_bps / 10_000.0 + cost.fx_fee_rate

    index_r = _equal_weight_index_returns(prices)
    index_level = (1.0 + index_r).cumprod()
    sma = index_level.rolling(trend_days).mean()

    # レジーム: 指数水準 > 長期移動平均 なら上向き。前日判定→翌日適用（ルックアヘッド回避）。
    regime_up = (index_level > sma)
    invested = regime_up.shift(1)
    # 移動平均が出そろう前は判断材料がないので投資（=持ち続けと同じ）に倒す。
    invested = invested.where(sma.shift(1).notna(), other=True).astype(bool)

    dates = index_r.index
    bh_nav = initial_cash
    df_nav = initial_cash
    prev_invested = False
    bh_records, df_records = [], []
    invested_days = 0

    for i, date in enumerate(dates):
        r = float(index_r.loc[date])
        # 持ち続け: 常に投資。
        bh_nav *= (1.0 + r)
        # 防御: 投資している日だけ指数リターンを取り、現金の日は0。
        inv = bool(invested.loc[date])
        if inv:
            df_nav *= (1.0 + r)
            invested_days += 1
        # 投資有無が切り替わる日は全建玉を売買 → ターンオーバーコスト。
        if inv != prev_invested:
            df_nav *= (1.0 - cost_rate)
        prev_invested = inv

        bh_records.append((date, bh_nav))
        df_records.append((date, df_nav))

    bh_curve = pd.Series({d: v for d, v in bh_records}, name="buy_and_hold").sort_index()
    df_curve = pd.Series({d: v for d, v in df_records}, name="defensive").sort_index()

    return DefensiveResult(
        defensive_curve=df_curve,
        buy_hold_curve=bh_curve,
        defensive_metrics=compute_metrics(df_curve, [], currency),
        buy_hold_metrics=compute_metrics(bh_curve, [], currency),
        days_invested_pct=100.0 * invested_days / len(dates) if len(dates) else 0.0,
    )

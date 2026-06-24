"""ロングショート（長短）戦略の評価モジュール — 研究用シミュレーション。

横断モメンタムの順位を使い、強い上位 top_k を「買い(ロング)」、弱い下位 bottom_k を
「空売り(ショート)」する“マーケットニュートラル”ポートフォリオの成績を計算する。
相場全体の上下を打ち消し、「強い銘柄が弱い銘柄より良ければ勝つ」形をめざす。

★位置づけ（重要）:
  これは研究用の評価で、端株（小数株）と空売りが自由にできる前提のウェイトベース計算。
  整数株丸めや貸株コスト・規制は簡略化している。1万円・単元未満株で実際に執行できる
  「ロング専用」パス（BacktestEngine）とは別物。本番運用にショートは想定しない。

計算方式（ウェイト/小数株ベースで正確に）:
  - リバランス日ごとに、スコア上位を等金額ロング・下位を等金額ショート。
    ネットはゼロ（買いと売りの金額を同額）、グロス(総建玉)= gross（既定1.0）。
  - 各銘柄の建玉は小数株で保持（ショートは負の株数）。リバランス間は建玉を固定し、
    日々の損益 = Σ 株数 ×（当日終値 − 前日終値）で時価評価（ショートは値上がりで損）。
  - リバランス時の売買金額（ターンオーバー）に取引コスト（手数料+スリッページ+為替）を課す。

★ルックアヘッドなし: スコアは過去の終値のみ。建玉はその日のスコアで決め、損益は翌日以降に出る。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd

from autotrade.backtest.metrics import compute_metrics
from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel


@dataclass
class LongShortResult:
    equity_curve: pd.Series
    metrics: Dict[str, float] = field(default_factory=dict)
    avg_long_names: float = 0.0
    avg_short_names: float = 0.0
    rebalances: int = 0


def _momentum_scores(prices: PriceData, lookback: int, skip: int) -> pd.DataFrame:
    closes = {sym: prices.frame(sym)["close"] for sym in prices.symbols}
    close_df = pd.DataFrame(closes)
    return close_df.shift(skip) / close_df.shift(lookback) - 1.0


def long_short_backtest(
    prices: PriceData,
    lookback: int = 250,
    skip: int = 20,
    top_k: int = 5,
    bottom_k: int = 5,
    rebalance_days: int = 21,
    gross: float = 1.0,
    cost_model: CostModel | None = None,
    initial_cash: float = 10_000.0,
    currency: str = "JPY",
) -> LongShortResult:
    cost = cost_model or CostModel()
    cost_rate = cost.commission_rate + cost.slippage_bps / 10_000.0 + cost.fx_fee_rate

    dates = prices.dates
    close_df = pd.DataFrame({sym: prices.frame(sym)["close"] for sym in prices.symbols})
    scores = _momentum_scores(prices, lookback, skip)

    symbols = list(prices.symbols)
    shares = {sym: 0.0 for sym in symbols}      # 建玉（負=ショート）
    nav = initial_cash
    equity_records: List[tuple] = []

    long_counts: List[int] = []
    short_counts: List[int] = []
    n_rebal = 0
    first_rebal_done = False

    for i, date in enumerate(dates):
        # 1. 時価評価（前日からの損益を反映）。最初の評価日は損益ゼロ。
        if i > 0:
            prev = dates[i - 1]
            pnl = 0.0
            for sym in symbols:
                if shares[sym] == 0.0:
                    continue
                p_now = close_df.at[date, sym]
                p_prev = close_df.at[prev, sym]
                if pd.notna(p_now) and pd.notna(p_prev):
                    pnl += shares[sym] * (p_now - p_prev)
            nav += pnl

        # 2. リバランス（rebalance_days ごと、かつスコアが出そろってから）。
        is_rebal = (i >= lookback) and ((i - lookback) % rebalance_days == 0)
        if is_rebal:
            row = scores.loc[date]
            valid = row[row.notna() & close_df.loc[date].notna()]
            if len(valid) >= (top_k + bottom_k):
                ranked = valid.sort_values(ascending=False)
                longs = list(ranked.index[:top_k])
                shorts = list(ranked.index[-bottom_k:])

                # 目標建玉（小数株）。ロング側合計 +gross/2、ショート側合計 -gross/2 → ネット0。
                target_shares = {sym: 0.0 for sym in symbols}
                long_w = (gross / 2.0) / len(longs)
                short_w = (gross / 2.0) / len(shorts)
                for sym in longs:
                    target_shares[sym] = (long_w * nav) / close_df.at[date, sym]
                for sym in shorts:
                    target_shares[sym] = -(short_w * nav) / close_df.at[date, sym]

                # ターンオーバー（建玉変更の売買金額）にコストを課す。
                turnover = 0.0
                for sym in symbols:
                    px = close_df.at[date, sym]
                    if pd.notna(px):
                        turnover += abs(target_shares[sym] - shares[sym]) * px
                nav -= turnover * cost_rate

                shares = target_shares
                long_counts.append(len(longs))
                short_counts.append(len(shorts))
                n_rebal += 1
                first_rebal_done = True

        if first_rebal_done:
            equity_records.append((date, nav))

    equity = pd.Series({d: v for d, v in equity_records}, name="long_short").sort_index()
    metrics = compute_metrics(equity, [], currency)
    return LongShortResult(
        equity_curve=equity,
        metrics=metrics,
        avg_long_names=float(np.mean(long_counts)) if long_counts else 0.0,
        avg_short_names=float(np.mean(short_counts)) if short_counts else 0.0,
        rebalances=n_rebal,
    )

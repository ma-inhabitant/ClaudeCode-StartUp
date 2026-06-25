"""積立（分散バスケットの買い増し）支援。

検証の結論「価格ベースの売買では持ち続けに勝てない」を受けた“現実路線”の機能。
売買タイミングを当てにいかず、**分散したバスケットを毎月コツコツ買い増して持ち続ける**
（ドルコスト平均法）。本モジュールは2つを提供する:

  1. plan_purchases … 「今いくらで、どの銘柄を何株買えば分散に近づくか」の“お買い物リスト”。
     上がりそうな銘柄の予想ではなく、**目標の分散比率に最も足りない銘柄から1株ずつ**埋める。
     整数株（1株刻み）・予算・取引コストを守る。日本株の半自動運用（手動発注）にそのまま使える。
  2. simulate_accumulation … 「初期資金＋毎月一定額を積み立てて持ち続けたら、過去データで
     資産はどう育ったか」を再現。長期・複利の効果を確認する（売りはしない）。

★ルックアヘッドなし: 各時点で入手可能な価格のみ使用。予想は行わない。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel
from autotrade.types import Side


def _one_share_cost(price: float, cost: CostModel) -> float:
    """1株を買うのに必要な金額（スリッページ＋手数料＋為替手数料込み）。"""
    fill = cost.fill_price(price, Side.BUY)
    return fill + cost.commission(fill) + cost.fx_fee(fill)


def plan_purchases(
    prices_today: Dict[str, float],
    holdings: Dict[str, float],
    budget: float,
    cost_model: CostModel,
    target_weights: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, int], float, float]:
    """予算内で「分散に最も足りない銘柄から1株ずつ」買うお買い物リストを作る。

    返り値: (買う株数 {銘柄: 株数}, 使った金額, 余った金額)
    """
    syms = list(prices_today.keys())
    if target_weights is None:
        target_weights = {s: 1.0 / len(syms) for s in syms}  # 既定は等金額（均等分散）

    buys: Dict[str, int] = defaultdict(int)
    remaining = budget
    spent = 0.0

    # 「最も足りない（目標比率との差が大きい）銘柄を1株ずつ」を、買えなくなるまで繰り返す。
    while True:
        port = {
            s: (holdings.get(s, 0.0) + buys[s]) * prices_today[s] for s in syms
        }
        total = sum(port.values())

        best_sym = None
        best_gap = float("-inf")
        for s in sorted(syms):  # sorted で同点時も決定的に
            cost1 = _one_share_cost(prices_today[s], cost_model)
            if cost1 > remaining or prices_today[s] <= 0:
                continue
            cur_w = port[s] / total if total > 0 else 0.0
            gap = target_weights.get(s, 0.0) - cur_w  # 正＝目標に足りない（買いたい）
            if gap > best_gap:
                best_gap = gap
                best_sym = (s, cost1)

        if best_sym is None:
            break  # これ以上1株も買えない
        s, cost1 = best_sym
        buys[s] += 1
        remaining -= cost1
        spent += cost1

    # お買い物リストは「実際に買う銘柄（1株以上）」だけ返す。
    return {s: q for s, q in buys.items() if q > 0}, spent, remaining


@dataclass
class AccumulationResult:
    equity_curve: pd.Series          # 日々の資産（保有時価＋現金）
    contributed_curve: pd.Series     # 累計の投入額（自分で入れたお金）
    total_contributed: float
    final_value: float
    total_shares_bought: int
    months: int
    currency: str = "JPY"

    @property
    def gain(self) -> float:
        return self.final_value - self.total_contributed

    @property
    def gain_pct(self) -> float:
        return self.gain / self.total_contributed if self.total_contributed > 0 else 0.0


def _month_start_dates(dates: List[pd.Timestamp]) -> set:
    """各月の最初の営業日の集合（積立の実行日）。"""
    seen = set()
    starts = set()
    for d in dates:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            starts.add(d)
    return starts


def simulate_accumulation(
    prices: PriceData,
    initial_cash: float,
    monthly_contribution: float,
    cost_model: CostModel,
    target_weights: Optional[Dict[str, float]] = None,
    currency: str = "JPY",
) -> AccumulationResult:
    """初期資金＋毎月の積立でバスケットを買い増して持ち続けた場合の資産推移を再現。"""
    dates = prices.dates
    syms = prices.symbols
    month_starts = _month_start_dates(dates)
    first = dates[0]

    holdings: Dict[str, float] = {s: 0.0 for s in syms}
    cash = 0.0
    contributed = 0.0
    total_bought = 0
    months = 0

    eq_rec, cont_rec = [], []
    for d in dates:
        if d in month_starts:
            # 月初に入金（初回は初期資金、以降は毎月の積立額）。
            add = initial_cash if d == first else monthly_contribution
            cash += add
            contributed += add
            months += 1
            prices_today = {s: prices.price(s, d, "close") for s in syms if prices.has_price(s, d)}
            if prices_today:
                buys, spent, _ = plan_purchases(prices_today, holdings, cash, cost_model, target_weights)
                for s, q in buys.items():
                    holdings[s] += q
                    total_bought += q
                cash -= spent

        value = cash + sum(
            holdings[s] * prices.price(s, d, "close") for s in syms if prices.has_price(s, d)
        )
        eq_rec.append((d, value))
        cont_rec.append((d, contributed))

    return AccumulationResult(
        equity_curve=pd.Series({d: v for d, v in eq_rec}, name="equity").sort_index(),
        contributed_curve=pd.Series({d: v for d, v in cont_rec}, name="contributed").sort_index(),
        total_contributed=contributed,
        final_value=eq_rec[-1][1] if eq_rec else 0.0,
        total_shares_bought=total_bought,
        months=months,
        currency=currency,
    )

"""バイ&ホールド・ベンチマーク。

「戦略で売買せず、最初に等金額で全銘柄を買って、ただ持ち続けた場合」の
資産曲線を計算する。戦略がこれを上回らなければ、わざわざ売買する意味はない
（＝最も基本的な比較対象）。

設計:
  - 各銘柄に initial_cash / 銘柄数 を等金額で配分し、最初に売買可能になった日の
    始値で買って、期間末までホールド（リバランスなし）。
  - 取引コスト（手数料・スリッページ・為替手数料）はエントリー時に1回だけ織り込む。
    ★コストゼロ評価は行わない方針に合わせ、ベンチマークにもコストを課す。
  - 端株は使わず1株刻みで買う（少額・単元未満株運用の前提に合わせる）。買えない銘柄や
    余った現金はそのまま現金として保持する。
"""

from __future__ import annotations

import pandas as pd

from autotrade.data.base import PriceData
from autotrade.execution.base import CostModel
from autotrade.types import Side


def buy_and_hold_equity(
    prices: PriceData,
    cost_model: CostModel,
    initial_cash: float,
) -> pd.Series:
    """等金額バイ&ホールドの資産曲線（現地通貨建て）を返す。"""
    symbols = prices.symbols
    dates = prices.dates
    alloc = initial_cash / len(symbols)

    cash = initial_cash
    shares: dict[str, float] = {}

    # 各銘柄を「最初に価格がついた日の始値」で1回だけ買う。
    for sym in symbols:
        entry_date = next((d for d in dates if prices.has_price(sym, d)), None)
        if entry_date is None:
            continue
        open_price = prices.price(sym, entry_date, "open")
        fill_price = cost_model.fill_price(open_price, Side.BUY)  # スリッページ込み
        if fill_price <= 0:
            continue
        qty = int(alloc / fill_price)  # 1株刻み
        if qty < 1:
            continue
        trade_value = qty * fill_price
        fee = cost_model.commission(trade_value) + cost_model.fx_fee(trade_value)
        cash -= trade_value + fee
        shares[sym] = float(qty)

    # 日次の時価評価。
    records = []
    for d in dates:
        total = cash
        for sym, qty in shares.items():
            if prices.has_price(sym, d):
                total += qty * prices.price(sym, d, "close")
        records.append((d, total))

    return pd.Series({d: v for d, v in records}, name="buy_and_hold").sort_index()

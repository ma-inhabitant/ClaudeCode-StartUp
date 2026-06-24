"""横断モメンタム戦略（クロスセクショナル・ランキング）。

毎日、ユニバースの全銘柄を「過去の勢い（モメンタム）」でスコア付けして順位を付け、
上位 top_k 銘柄だけをロング（1）にする。全部に賭けず“強い銘柄に集中”する発想。

スコア = 「lookback 日前 → skip 日前」のリターン。
  直近 skip 日（既定20≒1か月）を除くのは、短期の反転（リバーサル）ノイズを避ける
  古典的なモメンタム設計（いわゆる 12-1 モメンタムの一般化）。

★ルックアヘッドなし: スコアは過去の終値だけ（shift で過去参照のみ）。各日のランキングも
その日のスコアだけで決める。未来は一切使わない。

★top_k はリスク設定の最大保有銘柄数（max_gross_exposure / per_symbol_max_weight）と
そろえること。例: per_symbol=0.10, max_gross=1.0 → 最大10銘柄なので top_k=10。
"""

from __future__ import annotations

from typing import Dict

import pandas as pd

from autotrade.strategies.base import Strategy


class CrossSectionalMomentumStrategy(Strategy):
    name = "xs_momentum"

    def __init__(self, lookback: int = 120, skip: int = 20, top_k: int = 10):
        self.lookback = int(lookback)
        self.skip = int(skip)
        self.top_k = int(top_k)

    def generate_signals(self, features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        # 各銘柄のモメンタムスコアを [日付 x 銘柄] にまとめる。
        scores = {}
        for sym, feat in features.items():
            close = feat["close"]
            scores[sym] = close.shift(self.skip) / close.shift(self.lookback) - 1.0
        score_df = pd.DataFrame(scores)

        # 各日でスコア降順に順位付け（スコアが NaN の銘柄は対象外＝順位なし）。
        # method="first" で同点を決定的に処理（再現性のため）。
        ranks = score_df.rank(axis=1, ascending=False, method="first")
        sig = (ranks <= self.top_k).astype("float")  # 上位 top_k のみ 1、他は 0
        return sig

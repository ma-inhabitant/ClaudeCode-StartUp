"""Strategy 抽象基底。

シグナル生成のみを行う純粋な変換。状態（資金・ポジション）は持たない。
出力は「目標ポジション方向」の DataFrame（index=日付, columns=銘柄）。
  1  … ロングを保有したい
  0  … ノーポジション（フラット）
Phase 1 はロングオンリー（空売りなし）。少額・初心者・単元未満株運用に合わせる。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_signals(self, features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """特徴量 → 目標ポジション（1=ロング, 0=フラット）。"""
        raise NotImplementedError

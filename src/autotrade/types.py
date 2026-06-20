"""共通のデータ型。

層をまたいで受け渡す最小限の値オブジェクトを定義する。
状態を持つロジックはここには置かない（Portfolio / Broker 側に置く）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """売買方向。"""

    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    """発注指示（まだ約定していない）。

    shares は株数。市場により最小発注単位が異なる（日本=単元未満なら1株、
    米国=1株 or 端株）。サイジングは RiskManager 側で丸める。
    """

    symbol: str
    side: Side
    shares: float
    reason: str = ""  # "entry" / "exit" / "stop" / "take_profit"


@dataclass
class Fill:
    """約定結果。コスト（手数料・スリッページ・為替手数料）込みで記録する。"""

    date: object
    symbol: str
    side: Side
    shares: float
    price: float  # スリッページ適用後の約定価格（現地通貨建て）
    commission: float
    fx_fee: float = 0.0
    reason: str = ""


@dataclass
class Position:
    """保有ポジション。損切り・利確の基準価格も保持する。"""

    symbol: str
    shares: float = 0.0
    entry_price: float = 0.0
    entry_date: object = None
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None

    @property
    def is_open(self) -> bool:
        return self.shares > 0

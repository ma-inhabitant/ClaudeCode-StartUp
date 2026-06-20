"""市場（マーケット）抽象 — 市場カレンダーと通貨/為替。

日本（JPX）と米国（US）で営業日・取引時間・通貨が異なるため抽象化する。
"""

from autotrade.markets.calendar import MarketCalendar, get_calendar
from autotrade.markets.currency import Currency, FlatFXRate

__all__ = ["MarketCalendar", "get_calendar", "Currency", "FlatFXRate"]

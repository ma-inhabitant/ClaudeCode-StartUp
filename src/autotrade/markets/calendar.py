"""市場カレンダー — 市場ごとの営業日・取引時間。

Phase 1 のバックテストは日足のため、データに存在する日付をそのまま営業日として扱う
簡易版で十分。ここでは市場メタ情報（通貨・取引時間・タイムゾーン）と、
将来 jpholiday / pandas-market-calendars 等へ差し替えるための IF を用意する。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketCalendar:
    """市場のメタ情報。"""

    market: str  # "JPX" / "US"
    currency: str  # "JPY" / "USD"
    timezone: str
    session: str  # 取引時間の説明（人間向け）
    lot_size: int  # 最小発注単位（株）。日本=単元未満株なら1、米国=1。

    def is_session_day(self, date) -> bool:
        # 簡易版: 週末を除く。祝日は将来のカレンダー実装で対応。
        import pandas as pd

        return pd.Timestamp(date).weekday() < 5


_CALENDARS = {
    "JPX": MarketCalendar(
        market="JPX",
        currency="JPY",
        timezone="Asia/Tokyo",
        session="09:00-11:30, 12:30-15:00 JST",
        lot_size=1,  # 単元未満株（S株/かぶミニ等）を前提に1株刻み
    ),
    "US": MarketCalendar(
        market="US",
        currency="USD",
        timezone="America/New_York",
        session="09:30-16:00 ET（日本時間の夜間）",
        lot_size=1,  # 米国株は1株単位（端株はさらに細かいが Phase 1 は1株刻み）
    ),
}


def get_calendar(market: str) -> MarketCalendar:
    key = market.upper()
    if key not in _CALENDARS:
        raise ValueError(f"未知の市場です: {market}（対応: {list(_CALENDARS)}）")
    return _CALENDARS[key]

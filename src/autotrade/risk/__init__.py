"""Risk / Portfolio 層 — 戦略から独立した最終防衛線。

戦略のバグがリスク層を貫通しない設計にする。
シグナル → サイジング・損切り/利確・最大DDブレーカー → 発注。
"""

from autotrade.risk.manager import RiskManager, RiskParams

__all__ = ["RiskManager", "RiskParams"]

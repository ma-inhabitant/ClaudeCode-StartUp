"""評価指標 — 資産曲線と取引履歴から各種メトリクスを算出。

すべて「コスト控除後」の資産曲線に基づく（楽観的評価を避ける）。
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def max_drawdown(equity: pd.Series) -> float:
    """最大ドローダウン（負の値, 例 -0.25 = -25%）。"""
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    return float(dd.min())


def compute_metrics(equity: pd.Series, trades: List, currency: str = "JPY") -> Dict[str, float]:
    equity = equity.astype(float).dropna()
    out: Dict[str, float] = {"currency": currency}
    if len(equity) < 2:
        return {**out, "note": "データが不足しています。"}

    initial = float(equity.iloc[0])
    final = float(equity.iloc[-1])
    rets = equity.pct_change().dropna()

    out["initial_equity"] = initial
    out["final_equity"] = final
    out["total_return"] = final / initial - 1.0

    n_days = len(equity)
    years = n_days / TRADING_DAYS
    out["cagr"] = (final / initial) ** (1.0 / years) - 1.0 if years > 0 and final > 0 else float("nan")

    std = float(rets.std())
    out["volatility_annual"] = std * np.sqrt(TRADING_DAYS)
    out["sharpe"] = (
        float(rets.mean()) / std * np.sqrt(TRADING_DAYS) if std > 0 else float("nan")
    )
    out["max_drawdown"] = max_drawdown(equity)

    n_trades = len(trades)
    out["num_trades"] = n_trades
    if n_trades > 0:
        pnls = np.array([t.pnl for t in trades], dtype=float)
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        out["win_rate"] = float(len(wins) / n_trades)
        out["avg_win"] = float(wins.mean()) if len(wins) else 0.0
        out["avg_loss"] = float(losses.mean()) if len(losses) else 0.0
        gross_win = float(wins.sum())
        gross_loss = float(-losses.sum())
        out["profit_factor"] = gross_win / gross_loss if gross_loss > 0 else float("inf")
        out["total_realized_pnl"] = float(pnls.sum())
    else:
        out["win_rate"] = float("nan")
    return out


def format_comparison(strategy: Dict[str, float], benchmark: Dict[str, float]) -> str:
    """戦略 vs バイ&ホールドの対比表（CLI 表示用）。

    「ただ買って持ち続けた場合」に戦略が勝てているかを一目で分かるようにする。
    """
    pct = lambda x: f"{x * 100:>+7.2f}%" if isinstance(x, (int, float)) and pd.notna(x) else "    n/a"
    num = lambda x: f"{x:>8.2f}" if isinstance(x, (int, float)) and pd.notna(x) else "    n/a"

    def row(label, key, fmt):
        return f"  {label:18} {fmt(strategy.get(key)):>10} | {fmt(benchmark.get(key)):>10}"

    total_diff = (strategy.get("total_return", 0) or 0) - (benchmark.get("total_return", 0) or 0)
    verdict = (
        "戦略の勝ち（持ち続けるより良い）" if total_diff > 0
        else "戦略の負け（ただ持ち続けた方が良い）"
    )
    lines = [
        "==== 戦略 vs バイ&ホールド（持ち続けた場合） ====",
        f"  {'指標':16} {'戦略':>12} | {'持ち続け':>10}",
        "  " + "-" * 40,
        row("トータルリターン", "total_return", pct),
        row("CAGR(年率)", "cagr", pct),
        row("シャープレシオ", "sharpe", num),
        row("最大DD", "max_drawdown", pct),
        "  " + "-" * 40,
        f"  差(リターン)      : {total_diff * 100:>+7.2f}%  → {verdict}",
    ]
    return "\n".join(lines)


def format_metrics(metrics: Dict[str, float]) -> str:
    """人間向けに整形（CLI 表示用）。"""
    cur = metrics.get("currency", "")
    pct = lambda x: f"{x * 100:,.2f}%" if isinstance(x, (int, float)) and pd.notna(x) else "n/a"
    money = lambda x: f"{x:,.0f} {cur}" if isinstance(x, (int, float)) and pd.notna(x) else "n/a"
    lines = [
        "==== バックテスト結果 ====",
        f"初期資産        : {money(metrics.get('initial_equity'))}",
        f"最終資産        : {money(metrics.get('final_equity'))}",
        f"トータルリターン: {pct(metrics.get('total_return'))}",
        f"CAGR(年率)      : {pct(metrics.get('cagr'))}",
        f"年率ボラ        : {pct(metrics.get('volatility_annual'))}",
        f"シャープレシオ  : {metrics.get('sharpe', float('nan')):.2f}",
        f"最大DD          : {pct(metrics.get('max_drawdown'))}",
        f"取引回数        : {metrics.get('num_trades', 0)}",
        f"勝率            : {pct(metrics.get('win_rate'))}",
        f"プロフィットF   : {metrics.get('profit_factor', float('nan')):.2f}",
        f"実現損益(合計)  : {money(metrics.get('total_realized_pnl'))}",
    ]
    return "\n".join(lines)

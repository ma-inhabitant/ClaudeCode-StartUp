"""ウォークフォワード検証。

「前半のデータで設定（パラメータ）を決め、後半の“見たことがないデータ”で
答え合わせをする」検証方法。これを繰り返し、つなぎ合わせた“本番想定”の成績を見る。

なぜ必要か:
  普通のバックテストは「全期間で一番良かった設定」を後から選びがちで、
  それは“過去に都合よく合わせただけ”（オーバーフィッティング）かもしれない。
  ウォークフォワードは設定選びに使うデータと評価に使うデータを分けるので、
  「本当に通用する設定か」を正直に測れる。

手順（1フォールド）:
  1. 学習窓（例: 直近2年）の成績が最も良いパラメータを選ぶ（=過去だけで決定）。
  2. その設定を、続くテスト窓（例: 次の1年, 学習に未使用）に適用して成績を記録。
  3. 窓を1年ぶんずらして繰り返す。
  4. 各テスト窓の成績をつなぎ合わせ、全体の“本番想定”成績を得る。

★ルックアヘッドなし: パラメータは必ず「テスト窓より前のデータ」だけで決める。

実装メモ:
  ルールベース戦略は「学習」で係数が変わるわけではないので、各パラメータ組は
  全期間で1回だけ実行すれば足りる（指標のウォームアップも自然に効く）。その資産
  曲線を学習窓/テスト窓に“切り出して”使う。学習窓の成績で最良の組を選び、同じ組の
  テスト窓リターンを採用する。テスト窓リターンをフォールド横断で連結し、初期資金から
  本番想定の資産曲線を再構成する。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from autotrade.backtest.benchmark import buy_and_hold_equity
from autotrade.backtest.metrics import compute_metrics
from autotrade.config import build_engine
from autotrade.data.base import DataSource, PriceData


@dataclass
class Fold:
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    chosen_params: Dict[str, Any] = field(default_factory=dict)
    train_sharpe: float = float("nan")
    test_return: float = float("nan")


@dataclass
class WalkForwardResult:
    oos_equity: pd.Series                # つなぎ合わせた本番想定(アウトオブサンプル)資産曲線
    oos_metrics: Dict[str, float]
    benchmark_equity: pd.Series          # 同じ評価区間のバイ&ホールド
    benchmark_metrics: Dict[str, float]
    folds: List[Fold]


def _apply_params(base_cfg: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """パラメータ組を設定 dict に反映したコピーを返す。

    対応キー: strategy(戦略名), sma_fast, sma_slow, sma_trend, rsi_max。
    """
    cfg = copy.deepcopy(base_cfg)
    if "strategy" in params:
        cfg.setdefault("strategy", {})["name"] = params["strategy"]
    if "rsi_max" in params:
        cfg.setdefault("strategy", {})["rsi_max"] = params["rsi_max"]
    for k in ("sma_fast", "sma_slow", "sma_trend"):
        if k in params:
            cfg.setdefault("features", {})[k] = params[k]
    return cfg


def _slice_metric(equity: pd.Series, start, end) -> float:
    """[start, end] のシャープレシオ（学習窓の良し悪し判定に使う）。"""
    seg = equity[(equity.index >= start) & (equity.index <= end)]
    m = compute_metrics(seg, [])
    return m.get("sharpe", float("nan"))


def _make_folds(
    dates: List[pd.Timestamp], train_years: int, test_years: int
) -> List[Fold]:
    start, end = dates[0], dates[-1]
    folds: List[Fold] = []
    test_start = start + pd.DateOffset(years=train_years)
    while test_start < end:
        test_end = min(test_start + pd.DateOffset(years=test_years), end)
        # テスト窓が極端に短い最後の半端は捨てる。
        if (test_end - test_start).days < 90:
            break
        folds.append(Fold(train_start=start, test_start=test_start, test_end=test_end))
        test_start = test_end
    return folds


def walk_forward(
    cfg: Dict[str, Any],
    param_grid: List[Dict[str, Any]],
    train_years: int = 2,
    test_years: int = 1,
    prices: Optional[PriceData] = None,
) -> WalkForwardResult:
    # 1) データは一度だけ取得して全パラメータ組で使い回す。
    if prices is None:
        engine0 = build_engine(cfg)
        prices = engine0.prices

    initial_cash = float(cfg.get("initial_cash", 10_000))

    # 2) 各パラメータ組を全期間で1回ずつ実行し、資産曲線をキャッシュ。
    curves: List[pd.Series] = []
    for params in param_grid:
        eng = build_engine(_apply_params(cfg, params), prices=prices)
        curves.append(eng.run().equity_curve)

    # 3) フォールドごとに学習窓で最良を選び、テスト窓リターンを採用。
    dates = prices.dates
    folds = _make_folds(dates, train_years, test_years)
    oos_returns: List[pd.Series] = []
    for fold in folds:
        scores = [
            _slice_metric(curve, fold.train_start, fold.test_start)
            for curve in curves
        ]
        # シャープが NaN（取引なし等）は最下位扱い。
        best = max(
            range(len(scores)),
            key=lambda i: (scores[i] if pd.notna(scores[i]) else float("-inf")),
        )
        fold.chosen_params = param_grid[best]
        fold.train_sharpe = scores[best]

        seg = curves[best]
        seg = seg[(seg.index > fold.test_start) & (seg.index <= fold.test_end)]
        rets = seg.pct_change().dropna()
        oos_returns.append(rets)
        fold.test_return = float((1.0 + rets).prod() - 1.0) if len(rets) else float("nan")

    # 4) テスト窓リターンを連結し、初期資金から本番想定の資産曲線を再構成。
    if oos_returns:
        all_rets = pd.concat(oos_returns).sort_index()
        oos_equity = (1.0 + all_rets).cumprod() * initial_cash
        oos_equity.name = "walkforward_oos"
    else:
        oos_equity = pd.Series(dtype=float, name="walkforward_oos")

    oos_metrics = compute_metrics(oos_equity, [], cfg_currency(cfg))

    # 5) 同じ評価区間のバイ&ホールドと比較。
    bench_full = buy_and_hold_equity(prices, _cost_from_cfg(cfg), initial_cash)
    if folds:
        lo, hi = folds[0].test_start, folds[-1].test_end
        bench = bench_full[(bench_full.index >= lo) & (bench_full.index <= hi)]
    else:
        bench = bench_full
    bench_metrics = compute_metrics(bench, [], cfg_currency(cfg))

    return WalkForwardResult(
        oos_equity=oos_equity,
        oos_metrics=oos_metrics,
        benchmark_equity=bench,
        benchmark_metrics=bench_metrics,
        folds=folds,
    )


def _param_label(p: Dict[str, Any]) -> str:
    parts = [str(p.get("strategy", "sma_crossover"))]
    for k in ("sma_fast", "sma_slow", "sma_trend", "rsi_max"):
        if k in p:
            parts.append(f"{k}={p[k]}")
    return " ".join(parts)


def format_walkforward_result(result: WalkForwardResult) -> str:
    pct = lambda x: f"{x * 100:>+7.2f}%" if isinstance(x, (int, float)) and pd.notna(x) else "    n/a"
    num = lambda x: f"{x:>7.2f}" if isinstance(x, (int, float)) and pd.notna(x) else "    n/a"
    lines = ["==== ウォークフォワード検証（フォールド別） ===="]
    for i, f in enumerate(result.folds, 1):
        ts = f.test_start.date()
        te = f.test_end.date()
        lines.append(
            f"  Fold{i} テスト {ts}〜{te}: 採用={_param_label(f.chosen_params)}"
        )
        lines.append(
            f"        学習窓シャープ={num(f.train_sharpe)} / テスト窓リターン={pct(f.test_return)}"
        )

    s, b = result.oos_metrics, result.benchmark_metrics
    lines += [
        "",
        "==== 本番想定(アウトオブサンプル) vs バイ&ホールド ====",
        f"  {'指標':16} {'WF戦略':>12} | {'持ち続け':>10}",
        "  " + "-" * 40,
        f"  {'トータルリターン':18} {pct(s.get('total_return')):>10} | {pct(b.get('total_return')):>10}",
        f"  {'CAGR(年率)':18} {pct(s.get('cagr')):>10} | {pct(b.get('cagr')):>10}",
        f"  {'シャープレシオ':18} {num(s.get('sharpe')):>10} | {num(b.get('sharpe')):>10}",
        f"  {'最大DD':18} {pct(s.get('max_drawdown')):>10} | {pct(b.get('max_drawdown')):>10}",
    ]
    diff = (s.get("total_return", 0) or 0) - (b.get("total_return", 0) or 0)
    verdict = "戦略の勝ち" if diff > 0 else "戦略の負け（持ち続けが優位）"
    lines.append("  " + "-" * 40)
    lines.append(f"  差(リターン)      : {diff * 100:>+7.2f}%  → {verdict}")
    return "\n".join(lines)


def cfg_currency(cfg: Dict[str, Any]) -> str:
    from autotrade.markets.calendar import get_calendar

    return get_calendar(cfg.get("market", "JPX")).currency


def _cost_from_cfg(cfg: Dict[str, Any]):
    from autotrade.execution.base import CostModel

    return CostModel(**(cfg.get("cost", {}) or {}))

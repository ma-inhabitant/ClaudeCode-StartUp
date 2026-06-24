"""CLI エントリポイント。

使い方:
    python -m autotrade.cli backtest --config config/jp.yaml
    python -m autotrade.cli backtest --config config/jp.yaml --save-equity output/equity.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from autotrade.backtest.metrics import format_comparison, format_metrics
from autotrade.backtest.walkforward import format_walkforward_result, walk_forward
from autotrade.config import build_engine, load_config

# ウォークフォワードで試すパラメータ候補（学習窓で最良を選ぶ）。
DEFAULT_PARAM_GRID = [
    {"strategy": "sma_crossover", "sma_fast": 10, "sma_slow": 50},
    {"strategy": "sma_crossover", "sma_fast": 20, "sma_slow": 50},
    {"strategy": "sma_crossover", "sma_fast": 20, "sma_slow": 100},
    {"strategy": "trend_filter", "sma_fast": 20, "sma_slow": 50, "sma_trend": 100},
    {"strategy": "trend_filter", "sma_fast": 20, "sma_slow": 50, "sma_trend": 200},
    {"strategy": "trend_filter", "sma_fast": 10, "sma_slow": 50, "sma_trend": 100},
]


def cmd_backtest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    # --strategy が指定されたら設定ファイルの戦略名を上書き（比較用）。
    if args.strategy:
        cfg.setdefault("strategy", {})["name"] = args.strategy
    engine = build_engine(cfg)
    result = engine.run()

    print(format_metrics(result.metrics))
    print(f"\n約定回数: {len(result.fills)} / クローズ取引: {len(result.trades)}")

    if result.benchmark_metrics:
        print()
        print(format_comparison(result.metrics, result.benchmark_metrics))

    if args.save_equity:
        out = Path(args.save_equity)
        out.parent.mkdir(parents=True, exist_ok=True)
        result.equity_curve.to_csv(out, header=True)
        print(f"資産曲線を保存しました: {out}")
    return 0


def cmd_defensive(args: argparse.Namespace) -> int:
    from autotrade.backtest.defensive import defensive_overlay
    from autotrade.backtest.metrics import format_comparison
    from autotrade.execution.base import CostModel
    from autotrade.markets.calendar import get_calendar

    cfg = load_config(args.config)
    if args.start or args.end:
        cfg.setdefault("period", {})
        if args.start:
            cfg["period"]["start"] = args.start
        if args.end:
            cfg["period"]["end"] = args.end

    engine = build_engine(cfg)
    prices = engine.prices
    currency = get_calendar(cfg.get("market", "JPX")).currency
    cost = CostModel(**(cfg.get("cost", {}) or {}))
    initial = float(cfg.get("initial_cash", 10_000))

    res = defensive_overlay(
        prices, trend_days=args.trend_days, cost_model=cost,
        initial_cash=initial, currency=currency,
    )
    print(format_metrics(res.defensive_metrics))
    print(f"\n投資していた日の割合: {res.days_invested_pct:.1f}%（残りは現金で回避）")
    print()
    # ここでの「持ち続け」は同じ等金額インデックス（防御オーバーレイとの差は降りる判断だけ）。
    print(format_comparison(res.defensive_metrics, res.buy_hold_metrics))

    if args.save_equity:
        out = Path(args.save_equity)
        out.parent.mkdir(parents=True, exist_ok=True)
        df = res.defensive_curve.to_frame()
        df["buy_and_hold"] = res.buy_hold_curve
        df.to_csv(out, header=True)
        print(f"\n資産曲線を保存しました: {out}")
    return 0


def cmd_longshort(args: argparse.Namespace) -> int:
    from autotrade.backtest.benchmark import buy_and_hold_equity
    from autotrade.backtest.long_short import long_short_backtest
    from autotrade.backtest.metrics import format_comparison
    from autotrade.execution.base import CostModel
    from autotrade.markets.calendar import get_calendar

    cfg = load_config(args.config)
    if args.start or args.end:
        cfg.setdefault("period", {})
        if args.start:
            cfg["period"]["start"] = args.start
        if args.end:
            cfg["period"]["end"] = args.end

    engine = build_engine(cfg)  # データ取得とユニバース整列を流用
    prices = engine.prices
    currency = get_calendar(cfg.get("market", "JPX")).currency
    cost = CostModel(**(cfg.get("cost", {}) or {}))
    initial = float(cfg.get("initial_cash", 10_000))

    res = long_short_backtest(
        prices,
        lookback=args.lookback,
        skip=args.skip,
        top_k=args.top_k,
        bottom_k=args.bottom_k,
        rebalance_days=args.rebalance_days,
        gross=args.gross,
        cost_model=cost,
        initial_cash=initial,
        currency=currency,
    )
    print(format_metrics(res.metrics))
    print(
        f"\nリバランス回数: {res.rebalances} / "
        f"平均ロング {res.avg_long_names:.0f}銘柄・平均ショート {res.avg_short_names:.0f}銘柄"
    )

    # 同じ評価区間のバイ&ホールドと比較。
    if len(res.equity_curve) > 0:
        bench = buy_and_hold_equity(prices, cost, initial)
        lo, hi = res.equity_curve.index[0], res.equity_curve.index[-1]
        bench = bench[(bench.index >= lo) & (bench.index <= hi)]
        from autotrade.backtest.metrics import compute_metrics

        print()
        print(format_comparison(res.metrics, compute_metrics(bench, [], currency)))

    if args.save_equity:
        out = Path(args.save_equity)
        out.parent.mkdir(parents=True, exist_ok=True)
        res.equity_curve.to_csv(out, header=True)
        print(f"\n資産曲線を保存しました: {out}")
    return 0


def cmd_walkforward(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    # 期間の上書き（フォールド数を増やすため長い履歴を使うと有効）。
    if args.start or args.end:
        cfg.setdefault("period", {})
        if args.start:
            cfg["period"]["start"] = args.start
        if args.end:
            cfg["period"]["end"] = args.end

    result = walk_forward(
        cfg,
        DEFAULT_PARAM_GRID,
        train_years=args.train_years,
        test_years=args.test_years,
    )
    print(format_walkforward_result(result))

    if args.save_equity:
        out = Path(args.save_equity)
        out.parent.mkdir(parents=True, exist_ok=True)
        df = result.oos_equity.to_frame()
        df["buy_and_hold"] = result.benchmark_equity
        df.to_csv(out, header=True)
        print(f"\n資産曲線を保存しました: {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="autotrade", description="日本株・米国株 自動売買システム（Phase 1: バックテスト）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="設定ファイルでバックテストを実行")
    bt.add_argument("--config", required=True, help="設定 YAML のパス（例: config/jp.yaml）")
    bt.add_argument(
        "--strategy",
        help="戦略名を設定ファイルから上書き（例: sma_crossover / trend_filter）",
    )
    bt.add_argument("--save-equity", help="資産曲線を CSV 出力するパス（任意）")
    bt.set_defaults(func=cmd_backtest)

    wf = sub.add_parser("walkforward", help="ウォークフォワード検証（前半で設定決定→後半で答え合わせ）")
    wf.add_argument("--config", required=True, help="設定 YAML のパス")
    wf.add_argument("--train-years", type=int, default=2, help="学習窓の年数（既定2）")
    wf.add_argument("--test-years", type=int, default=1, help="テスト窓の年数（既定1）")
    wf.add_argument("--start", help="データ取得開始日を上書き（例: 2015-01-01。フォールドを増やせる）")
    wf.add_argument("--end", help="データ取得終了日を上書き")
    wf.add_argument("--save-equity", help="本番想定とベンチマークの資産曲線を CSV 出力（任意）")
    wf.set_defaults(func=cmd_walkforward)

    ls = sub.add_parser("longshort", help="ロングショート評価（上位ロング・下位ショート／研究用）")
    ls.add_argument("--config", required=True, help="設定 YAML のパス（例: config/us_xs.yaml）")
    ls.add_argument("--lookback", type=int, default=250, help="モメンタムの参照期間（日, 既定250）")
    ls.add_argument("--skip", type=int, default=20, help="直近で除外する日数（既定20）")
    ls.add_argument("--top-k", type=int, default=5, help="ロングする上位銘柄数（既定5）")
    ls.add_argument("--bottom-k", type=int, default=5, help="ショートする下位銘柄数（既定5）")
    ls.add_argument("--rebalance-days", type=int, default=21, help="リバランス間隔（日, 既定21≒月次）")
    ls.add_argument("--gross", type=float, default=1.0, help="総建玉（グロス, 既定1.0）")
    ls.add_argument("--start", help="データ取得開始日を上書き")
    ls.add_argument("--end", help="データ取得終了日を上書き")
    ls.add_argument("--save-equity", help="資産曲線を CSV 出力（任意）")
    ls.set_defaults(func=cmd_longshort)

    df = sub.add_parser("defensive", help="防御的オーバーレイ（インデックス＋暴落回避）の検証")
    df.add_argument("--config", required=True, help="設定 YAML のパス（例: config/us_xs.yaml）")
    df.add_argument("--trend-days", type=int, default=200, help="相場の向きを見る移動平均日数（既定200）")
    df.add_argument("--start", help="データ取得開始日を上書き")
    df.add_argument("--end", help="データ取得終了日を上書き")
    df.add_argument("--save-equity", help="防御と持ち続けの資産曲線を CSV 出力（任意）")
    df.set_defaults(func=cmd_defensive)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

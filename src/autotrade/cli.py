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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

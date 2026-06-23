"""CLI エントリポイント。

使い方:
    python -m autotrade.cli backtest --config config/jp.yaml
    python -m autotrade.cli backtest --config config/jp.yaml --save-equity output/equity.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from autotrade.backtest.metrics import format_comparison, format_metrics
from autotrade.config import build_engine, load_config


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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

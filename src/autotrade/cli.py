"""CLI エントリポイント。

使い方:
    python -m autotrade.cli backtest --config config/jp.yaml
    python -m autotrade.cli backtest --config config/jp.yaml --save-equity output/equity.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

from autotrade.backtest.metrics import format_metrics
from autotrade.config import build_engine, load_config


def cmd_backtest(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    engine = build_engine(cfg)
    result = engine.run()

    print(format_metrics(result.metrics))
    print(f"\n約定回数: {len(result.fills)} / クローズ取引: {len(result.trades)}")

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
    bt.add_argument("--save-equity", help="資産曲線を CSV 出力するパス（任意）")
    bt.set_defaults(func=cmd_backtest)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

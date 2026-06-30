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


def cmd_plan(args: argparse.Namespace) -> int:
    from autotrade.accumulation import (
        load_holdings,
        plan_purchases,
        write_holdings_csv,
        write_plan_csv,
    )
    from autotrade.execution.base import CostModel
    from autotrade.markets.calendar import get_calendar

    cfg = load_config(args.config)
    engine = build_engine(cfg)
    prices = engine.prices
    currency = get_calendar(cfg.get("market", "JPX")).currency
    cost = CostModel(**(cfg.get("cost", {}) or {}))

    # 「今日」＝取得データの最終営業日の終値で、予算ぶんのお買い物リストを作る。
    as_of = prices.dates[-1]
    prices_today = {s: prices.price(s, as_of, "close") for s in prices.symbols if prices.has_price(s, as_of)}

    # 現在の保有を読み込む（未指定なら保有ゼロから）。
    holdings = load_holdings(args.holdings) if args.holdings else {}
    unknown = sorted(set(holdings) - set(prices_today))
    if unknown:
        print(f"⚠ 保有CSVの次の銘柄はユニバース/価格に無いため無視します: {', '.join(unknown)}\n")
    holdings = {s: v for s, v in holdings.items() if s in prices_today}

    budget = float(args.budget)
    buys, spent, leftover = plan_purchases(prices_today, holdings, budget, cost)

    # 買い増し後の保有と比率（分散の現状確認）。
    n = len(prices_today)
    target = 1.0 / n if n else 0.0
    proj = {s: holdings.get(s, 0.0) + buys.get(s, 0.0) for s in prices_today}
    proj_total = sum(proj[s] * prices_today[s] for s in prices_today)

    print(f"==== 今月のお買い物リスト（基準日 {as_of.date()} / 予算 {budget:,.0f} {currency}）====")
    print("※ 上がる予想ではなく『分散バスケットを均等に近づける』ための割り当てです。")
    print(f"   目標比率 = 均等 {target*100:.1f}%/銘柄（全{n}銘柄）\n")

    if not buys:
        print("  予算が小さく、1株も買えませんでした。予算を増やすか低価格の銘柄を検討してください。\n")
    else:
        print("  【買う銘柄】")
        for s in sorted(buys):
            px = prices_today[s]
            print(f"    {s:<8} {buys[s]:>3}株  @ {px:,.2f}  ≈ {buys[s]*px:,.0f} {currency}")
        print(f"  ----  使う金額 ≈ {spent:,.0f} {currency} / 余り ≈ {leftover:,.0f} {currency}（コスト込み概算）\n")

    # 保有がある（or 買う）銘柄について、買い増し後の比率を表示。
    active = sorted(s for s in prices_today if proj[s] > 0)
    if active:
        print(f"  【買い増し後の保有と比率】（投資額 ≈ {proj_total:,.0f} {currency}）")
        for s in active:
            w = (proj[s] * prices_today[s] / proj_total * 100) if proj_total > 0 else 0.0
            cur = holdings.get(s, 0.0)
            add = buys.get(s, 0)
            mark = "←目標近辺" if abs(w - target * 100) <= target * 100 * 0.5 else ""
            print(f"    {s:<8} {cur:>4.0f}→{proj[s]:>4.0f}株  比率 {w:4.1f}%  {('(+'+str(add)+')') if add else '':<5}{mark}")
    held_names = sum(1 for s in prices_today if proj[s] > 0)
    print(f"\n  分散状況: {held_names}/{n} 銘柄を保有（均等まであと {max(0, n-held_names)} 銘柄）")

    if args.save:
        write_plan_csv(args.save, buys, prices_today)
        print(f"  お買い物リストを保存: {args.save}")
    if args.out_holdings:
        write_holdings_csv(args.out_holdings, proj)
        print(f"  買い増し後の保有を保存（次回 --holdings に使える）: {args.out_holdings}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from autotrade.accumulation import load_positions, portfolio_status
    from autotrade.markets.calendar import get_calendar

    cfg = load_config(args.config)
    engine = build_engine(cfg)
    prices = engine.prices
    currency = get_calendar(cfg.get("market", "JPX")).currency

    as_of = prices.dates[-1]
    prices_today = {s: prices.price(s, as_of, "close") for s in prices.symbols if prices.has_price(s, as_of)}

    positions = load_positions(args.holdings)
    if not positions:
        print("保有銘柄が読み込めませんでした（--holdings のCSVを確認してください）。")
        return 1
    unknown = sorted(set(positions) - set(prices_today))
    if unknown:
        print(f"⚠ 価格が取得できず評価から除外: {', '.join(unknown)}\n")

    st = portfolio_status(positions, prices_today, currency)

    print(f"==== ポートフォリオの現状（基準日 {as_of.date()}）====")
    pnl_hdr = "  損益" if st.total_cost is not None else ""
    print(f"  {'銘柄':<8} {'株数':>5} {'現在値':>10} {'評価額':>11} {'比率':>6}{pnl_hdr}")
    print("  " + "-" * (46 + (16 if st.total_cost is not None else 0)))
    for r in st.rows:
        line = f"  {r.symbol:<8} {r.shares:>5.0f} {r.price:>10,.1f} {r.market_value:>11,.0f} {r.weight*100:>5.1f}%"
        if r.pnl is not None:
            sign = "+" if r.pnl >= 0 else ""
            line += f"  {sign}{r.pnl:>,.0f}({sign}{r.pnl_pct*100:.1f}%)"
        print(line)
    print("  " + "-" * (46 + (16 if st.total_cost is not None else 0)))
    print(f"  保有銘柄数 : {st.n_names}")
    print(f"  評価額合計 : {st.total_value:,.0f} {currency}")
    if st.total_cost is not None:
        sign = "+" if st.total_pnl >= 0 else ""
        print(f"  投資元本   : {st.total_cost:,.0f} {currency}")
        print(f"  評価損益   : {sign}{st.total_pnl:,.0f} {currency}（{sign}{st.total_pnl_pct*100:.1f}%）")
    else:
        print("  （取得単価の列 avg_cost/取得単価 があれば損益も表示します）")
    return 0


def cmd_accumulate(args: argparse.Namespace) -> int:
    from autotrade.accumulation import simulate_accumulation
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
    initial = float(cfg.get("initial_cash", 50_000)) if args.initial is None else float(args.initial)

    res = simulate_accumulation(prices, initial, float(args.monthly), cost, currency=currency)

    years = res.months / 12.0
    print("==== 積立シミュレーション（分散バスケットを買い増して持ち続け）====")
    print(f"  期間          : {prices.dates[0].date()} 〜 {prices.dates[-1].date()}（約{years:.1f}年・{res.months}か月）")
    print(f"  初期資金      : {initial:,.0f} {currency}")
    print(f"  毎月の積立    : {float(args.monthly):,.0f} {currency}")
    print(f"  ----")
    print(f"  投入総額      : {res.total_contributed:,.0f} {currency}（自分で入れたお金）")
    print(f"  最終評価額    : {res.final_value:,.0f} {currency}")
    print(f"  増えた額      : {res.gain:,.0f} {currency}（{res.gain_pct*100:+.1f}%）")
    print(f"  買い付けた株数: 累計 {res.total_shares_bought} 株")

    if args.save_equity:
        out = Path(args.save_equity)
        out.parent.mkdir(parents=True, exist_ok=True)
        df = res.equity_curve.to_frame()
        df["contributed"] = res.contributed_curve
        df.to_csv(out, header=True)
        print(f"\n資産・投入額の推移を保存しました: {out}")
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

    pl = sub.add_parser("plan", help="今月のお買い物リスト（分散を保つ買い指示）を出力")
    pl.add_argument("--config", required=True, help="設定 YAML のパス（例: config/jp_xs.yaml）")
    pl.add_argument("--budget", type=float, required=True, help="今回の購入予算（現地通貨）")
    pl.add_argument("--holdings", help="現在の保有銘柄CSV（列: symbol,shares）。未指定なら保有ゼロから")
    pl.add_argument("--save", help="お買い物リストをCSV出力するパス（任意）")
    pl.add_argument("--out-holdings", help="買い増し後の保有をCSV出力（次回 --holdings に使える）")
    pl.set_defaults(func=cmd_plan)

    stt = sub.add_parser("status", help="保有の現状（評価額・比率・損益）を表示")
    stt.add_argument("--config", required=True, help="設定 YAML のパス（ユニバース/価格/通貨に使用）")
    stt.add_argument("--holdings", required=True, help="保有CSV（列: symbol,shares[,avg_cost]）")
    stt.set_defaults(func=cmd_status)

    ac = sub.add_parser("accumulate", help="積立シミュレーション（買い増して持ち続け）")
    ac.add_argument("--config", required=True, help="設定 YAML のパス（例: config/jp_xs.yaml）")
    ac.add_argument("--monthly", type=float, default=10_000, help="毎月の積立額（既定10000）")
    ac.add_argument("--initial", type=float, default=None, help="初期資金（既定は設定の initial_cash）")
    ac.add_argument("--start", help="データ取得開始日を上書き")
    ac.add_argument("--end", help="データ取得終了日を上書き")
    ac.add_argument("--save-equity", help="資産・投入額の推移を CSV 出力（任意）")
    ac.set_defaults(func=cmd_accumulate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

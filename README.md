# autotrade — 日本株・米国株 自動売買システム（Phase 1: バックテスト基盤）

機械学習を視野に入れた売買戦略を、**バックテスト → ペーパートレード → 本番運用**の順で
段階的に実用化していくマルチマーケット対応システムです。安全性を最優先とし、
Phase 1 では実発注コードを書きません（過去データでの検証のみ）。

> 📘 **株取引がはじめての方へ：** [`docs/初心者ガイド.md`](docs/初心者ガイド.md) からどうぞ。
> 要件・設計の全体像は [`CLAUDE.md`](CLAUDE.md) にあります。

## 特徴（Phase 1）

- **層の分離**：データ / 特徴量 / 戦略 / リスク / 約定 / 評価 を差し替え可能な IF で接続
- **マルチマーケット**：日本株（JPX）・米国株（US）を同一フレームで（市場カレンダー・通貨を抽象化）
- **リスク管理（必須）**：損切り/利確・ポジションサイズ・最大DDブレーカー・取引コスト/スリッページ
- **ルックアヘッドバイアス排除**：シグナルは当日終値まで、約定は翌日始値
- **再現性**：乱数シード固定。**ネット不要の合成データ**で誰でもすぐ動かせる

## セットアップ

```bash
pip install -e .            # 本体（pandas/numpy/pyyaml）
pip install -e ".[dev]"     # テスト用に pytest も入れる
pip install -e ".[data]"    # 実データ取得に yfinance を使う場合
```

## 使い方

```bash
# 日本株（既定は合成データ。ネット不要ですぐ動く）
python -m autotrade.cli backtest --config config/jp.yaml

# 米国株（為替手数料込みのコストモデル）
python -m autotrade.cli backtest --config config/us.yaml

# 資産曲線を CSV 保存
python -m autotrade.cli backtest --config config/jp.yaml --save-equity output/equity.csv
```

実データ（yfinance）を使うときは、実データ用の設定で実行します:

```bash
python -m autotrade.cli backtest --config config/jp_real.yaml   # 実在の東証プライム銘柄
python -m autotrade.cli backtest --config config/us_real.yaml   # 実在の米国主要銘柄
```

> **Claude Code on the web 環境での注意:** ネットワーク egress が許可リスト制の場合、
> yfinance の接続先（`query1.finance.yahoo.com` / `query2.finance.yahoo.com` /
> `fc.yahoo.com`）を環境設定の許可リストに追加してからセッションを開始し直してください。
> 参考: https://code.claude.com/docs/en/claude-code-on-the-web

### Yahoo Finance が許可リスト外でも実データで動かす

egress 許可リストに `raw.githubusercontent.com` だけ通っていれば、実在の **S&P500 構成銘柄の
日足（2013-02-08〜2018-02-07、実データ）** を GitHub ホストのバンドルから取得して
バックテストできます（初回のみダウンロードし、`data/cache/` にキャッシュ）。

```bash
python -m autotrade.cli backtest --config config/us_real_sp500.yaml \
    --save-equity output/us_real_equity.csv
```

実行例（実データでの結果。良好な数値ではない点に注意 ＝ 戦略はまだベースライン）:

```
==== バックテスト結果 ====
初期資産        : 10,000 USD
最終資産        : 8,512 USD
トータルリターン: -14.88%
シャープレシオ  : -0.56
最大DD          : -22.95%
取引回数        : 37
勝率            : 32.43%
```

> データ元: [plotly/datasets `all_stocks_5yr.csv`](https://github.com/plotly/datasets)。
> 本格運用では日本=J-Quants、米国=IBKR/専用 API に差し替える前提です。

## テスト

```bash
pytest
```

リスク管理・約定シミュレーション・指標計算・エンジンの結合テストを含みます。

## ディレクトリ構成

```
src/autotrade/
├── data/        # DataSource（synthetic / csv / yfinance、将来 jquants・IBKR）
├── markets/     # MarketCalendar（JPX/US）, Currency / FX
├── features/    # 特徴量生成（SMA/RSI/ATR 等）
├── strategies/  # 戦略（baseline: 移動平均クロス。将来 ML）
├── risk/        # RiskManager（サイジング・損切り/利確・最大DD）
├── execution/   # Broker 抽象 + BacktestBroker（コストモデル）
├── backtest/    # BacktestEngine, Metrics
├── config.py    # YAML → 各層の組み立て
└── cli.py       # エントリポイント
```

## 注意（必読）

本システムは投資助言ではなく、損失リスクを伴います。バックテストの良好な結果は
将来の利益を保証しません。本番運用前に十分な検証と少額での試験運用を行ってください。
API キー・口座情報は `.env`（gitignore 済み）に置き、コミットしないでください。

# examples — 個別株サテライト運用の使い方

「分散バスケットを積立で買い増して持ち続ける」運用を、CLIで回すための入門サンプルです。
（※ 投資助言ではありません。損失リスクがあります。本番前に少額で試してください。）

## 1. 保有CSVを用意する

[`holdings_sample.csv`](holdings_sample.csv) をコピーして、自分の保有に書き換えます。

```csv
symbol,shares,avg_cost
7203.T,3,2000
9432.T,20,140
```

- `symbol` … 銘柄コード（日本株は `7203.T` のように `.T` を付ける）
- `shares` … 保有株数（単元未満株でOK。1株から）
- `avg_cost` … 平均取得単価（任意）。書くと評価損益も出る。分からなければ空でOK
- ヘッダは日本語（`銘柄,株数,取得単価`）でも読めます

## 2. 今の保有を点検する（status）

```powershell
# Python は PATH に無いのでフルパスで呼ぶ
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
& $py -m autotrade.cli status --config config/jp_xs.yaml --holdings examples/holdings_sample.csv
```

→ 銘柄ごとの評価額・比率・損益、全体の評価損益を表示。

## 3. 今月のお買い物リストを出す（plan）

```powershell
# 予算1万円で、保有を踏まえ「分散に足りない銘柄」を買い足す指示を出す
& $py -m autotrade.cli plan --config config/jp_xs.yaml --budget 10000 `
    --holdings examples/holdings_sample.csv `
    --save examples/buy_list.csv `
    --out-holdings examples/holdings_next.csv
```

→ `buy_list.csv`（買う銘柄）と `holdings_next.csv`（買い増し後の保有）が出力される。
実際にその通り単元未満株を手動発注し、来月は `holdings_next.csv` を `--holdings` に渡して繰り返す。

## 注意：価格は「設定期間の最終日」の終値

`config/jp_xs.yaml` の `period.end` が `2023-12-31` だと、現在値は 2023-12-29 の終値になります。
最新の株価で使いたい場合は、設定の `period.end` を最近の日付に変更してください（yfinance が直近まで取得します）。

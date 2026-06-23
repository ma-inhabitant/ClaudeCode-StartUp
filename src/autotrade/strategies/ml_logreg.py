"""機械学習戦略（ロジスティック回帰）。

「翌営業日からN日後までに上がるか？」をロジスティック回帰で予測し、
上がる確率が閾値を超えた銘柄をロング（1）にする。ルールベース戦略の比較対象。

★ルックアヘッドバイアスを徹底排除（拡張窓学習）:
  - 一定間隔(retrain_every)ごとに「その時点で結果が確定済みの過去データだけ」で
    学習し直す。学習に使えるのは「特徴量の日 t」かつ「t+N 日後の答えが決定日までに
    出ているサンプル」だけ。未来のラベルで学習しない。
  - 学習したモデルで、その先の予測ブロックのシグナルを出す（予測に使う特徴量は
    すべてその日までに入手可能なもの）。
  - 学習用データが十分たまるまで(min_train_days)はフラット（0）。

特徴量はすべてスケール非依存（価格水準に左右されない）に変換してから標準化する。
複数銘柄をまとめて1つのモデルで学習する（横断的に共通パターンを学ぶ＝サンプル増）。
"""

from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from autotrade.strategies.base import Strategy

# モデルに渡す特徴量の列（すべて価格水準に依存しない量）。
FEATURE_COLS = [
    "ret1",         # 前日比リターン
    "ret5",         # 5日リターン（短期モメンタム）
    "ret20",        # 20日リターン（中期モメンタム）
    "sma_fast_rel", # 株価に対する短期移動平均の位置
    "sma_slow_rel", # 同・長期
    "sma_trend_rel",# 同・超長期トレンド
    "rsi01",        # RSI を 0-1 に正規化
    "atr_rel",      # 株価に対するボラティリティ
]


class MLLogRegStrategy(Strategy):
    name = "ml_logreg"

    def __init__(
        self,
        forward_days: int = 5,
        retrain_every: int = 63,
        min_train_days: int = 252,
        prob_threshold: float = 0.55,
        seed: int = 42,
    ):
        self.forward_days = int(forward_days)
        self.retrain_every = int(retrain_every)
        self.min_train_days = int(min_train_days)
        self.prob_threshold = float(prob_threshold)
        self.seed = int(seed)

    # --- 特徴量・ラベルの組み立て ----------------------------------------
    def _design(self, feat: pd.DataFrame) -> pd.DataFrame:
        close = feat["close"]
        df = pd.DataFrame(index=feat.index)
        df["ret1"] = feat["ret1"]
        df["ret5"] = close.pct_change(5)
        df["ret20"] = close.pct_change(20)
        df["sma_fast_rel"] = feat["sma_fast"] / close - 1.0
        df["sma_slow_rel"] = feat["sma_slow"] / close - 1.0
        df["sma_trend_rel"] = feat["sma_trend"] / close - 1.0
        df["rsi01"] = feat["rsi"] / 100.0
        df["atr_rel"] = feat["atr"] / close
        return df

    def _forward_up(self, feat: pd.DataFrame) -> pd.Series:
        """N日後までに上がれば1、そうでなければ0（学習ラベル）。未来参照は学習時のみ。"""
        close = feat["close"]
        fwd = close.shift(-self.forward_days) / close - 1.0
        return (fwd > 0).astype("float").where(fwd.notna(), other=np.nan)

    def generate_signals(self, features: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        symbols: List[str] = list(features.keys())
        dates = features[symbols[0]].index
        n = len(dates)

        # 各銘柄の特徴量行列(X)とラベル(y)を事前計算（numpy 化して高速に）。
        X_by_sym, y_by_sym, valid_by_sym = {}, {}, {}
        for sym in symbols:
            feat = features[sym]
            X = self._design(feat)
            y = self._forward_up(feat)
            X_by_sym[sym] = X[FEATURE_COLS].to_numpy(dtype=float)
            y_by_sym[sym] = y.to_numpy(dtype=float)
            x_ok = ~np.isnan(X_by_sym[sym]).any(axis=1)
            valid_by_sym[sym] = x_ok  # 予測に使える行（特徴量がそろっている）

        signals = {sym: np.full(n, np.nan) for sym in symbols}

        # 拡張窓: min_train_days から retrain_every 間隔で学習→その先を予測。
        for block_start in range(self.min_train_days, n, self.retrain_every):
            block_end = min(block_start + self.retrain_every, n)
            # 学習: t+forward_days <= block_start のサンプルのみ（答えが確定済み＝リークなし）。
            train_limit = block_start - self.forward_days
            if train_limit <= 0:
                continue
            X_tr, y_tr = [], []
            for sym in symbols:
                Xs, ys, ok = X_by_sym[sym], y_by_sym[sym], valid_by_sym[sym]
                rows = ok[:train_limit] & ~np.isnan(ys[:train_limit])
                if rows.any():
                    X_tr.append(Xs[:train_limit][rows])
                    y_tr.append(ys[:train_limit][rows])
            if not X_tr:
                continue
            X_tr = np.vstack(X_tr)
            y_tr = np.concatenate(y_tr)
            # 片方のクラスしかないと学習できない。十分なサンプルも要求。
            if len(np.unique(y_tr)) < 2 or len(y_tr) < 50:
                continue

            scaler = StandardScaler().fit(X_tr)
            model = LogisticRegression(max_iter=1000, random_state=self.seed)
            model.fit(scaler.transform(X_tr), y_tr)

            # 予測: ブロック内の各日について、特徴量がそろう銘柄のみ判定。
            for i in range(block_start, block_end):
                for sym in symbols:
                    if not valid_by_sym[sym][i]:
                        signals[sym][i] = 0.0
                        continue
                    x = X_by_sym[sym][i].reshape(1, -1)
                    p_up = float(model.predict_proba(scaler.transform(x))[0, 1])
                    signals[sym][i] = 1.0 if p_up >= self.prob_threshold else 0.0

        return pd.DataFrame(
            {sym: pd.Series(signals[sym], index=dates) for sym in symbols}
        )

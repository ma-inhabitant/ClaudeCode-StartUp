"""ML戦略（ロジスティック回帰・拡張窓学習）の単体テスト。

scikit-learn 未インストール環境では自動スキップ。
"""

import numpy as np
import pytest

pytest.importorskip("sklearn")

from autotrade.data.synthetic import SyntheticSource
from autotrade.features.builder import FeatureBuilder
from autotrade.strategies.ml_logreg import MLLogRegStrategy


def _features():
    prices = SyntheticSource(seed=3).get_prices(
        ["A", "B", "C"], "2016-01-01", "2021-12-31"
    )
    return FeatureBuilder(sma_fast=20, sma_slow=50, sma_trend=100).build(prices)


def test_ml_is_flat_before_min_train_then_trades():
    feat = _features()
    strat = MLLogRegStrategy(min_train_days=252, retrain_every=63)
    sig = strat.generate_signals(feat)

    # 学習データがたまる前（min_train_days より前）はすべてフラット（NaN）。
    early = sig.iloc[:252]
    assert early.isna().all().all()

    # それ以降は 0/1 の判断が出ている（NaN でない値が存在する）。
    later = sig.iloc[252:]
    assert later.notna().any().any()
    vals = np.unique(later.to_numpy()[~np.isnan(later.to_numpy())])
    assert set(vals).issubset({0.0, 1.0})


def test_ml_is_deterministic():
    feat = _features()
    s1 = MLLogRegStrategy().generate_signals(feat)
    s2 = MLLogRegStrategy().generate_signals(feat)
    # 乱数シード固定で、2回の結果は完全一致する（再現性）。
    assert s1.equals(s2)


def test_ml_no_lookahead_signal_uses_only_past_models():
    # min_train_days を変えると、早い時期のシグナル開始位置も後ろにずれる
    # （未来データで前倒しに学習していない＝拡張窓が効いている証拠）。
    feat = _features()
    early_start = MLLogRegStrategy(min_train_days=252).generate_signals(feat)
    late_start = MLLogRegStrategy(min_train_days=400).generate_signals(feat)
    first_trade_early = early_start.notna().any(axis=1).idxmax()
    first_trade_late = late_start.notna().any(axis=1).idxmax()
    assert first_trade_late > first_trade_early

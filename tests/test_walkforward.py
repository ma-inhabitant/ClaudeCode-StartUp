"""ウォークフォワード検証の単体テスト（合成データ・ネット不要）。"""

import pandas as pd

from autotrade.backtest.walkforward import _make_folds, walk_forward


def _synthetic_cfg():
    return {
        "market": "JPX",
        "data": {"source": "synthetic", "synthetic": {"seed": 7}},
        "universe": ["A", "B", "C"],
        "period": {"start": "2016-01-01", "end": "2022-12-31"},
        "initial_cash": 100000,
        "features": {"sma_fast": 20, "sma_slow": 50, "sma_trend": 100},
        "risk": {"max_drawdown_pct": 0.5},
        "cost": {"commission_rate": 0.001, "slippage_bps": 5},
    }


def test_make_folds_are_contiguous_and_out_of_sample():
    dates = list(pd.date_range("2016-01-01", "2022-12-31", freq="B"))
    folds = _make_folds(dates, train_years=2, test_years=1)
    assert len(folds) >= 3
    # テスト窓は学習開始より後に始まる（=未来データで設定を決めていない）。
    for f in folds:
        assert f.train_start < f.test_start <= f.test_end
    # 隣接フォールドのテスト窓は連続する（穴がない・重ならない）。
    for a, b in zip(folds, folds[1:]):
        assert a.test_end == b.test_start


def test_walk_forward_runs_and_picks_params():
    grid = [
        {"strategy": "sma_crossover", "sma_fast": 20, "sma_slow": 50},
        {"strategy": "trend_filter", "sma_fast": 20, "sma_slow": 50, "sma_trend": 100},
    ]
    res = walk_forward(_synthetic_cfg(), grid, train_years=2, test_years=1)
    assert len(res.folds) >= 2
    # 各フォールドでグリッド内のいずれかの設定が選ばれている。
    for f in res.folds:
        assert f.chosen_params in grid
    # 本番想定の資産曲線とベンチマークが算出されている。
    assert "total_return" in res.oos_metrics
    assert "total_return" in res.benchmark_metrics
    assert len(res.oos_equity) > 0

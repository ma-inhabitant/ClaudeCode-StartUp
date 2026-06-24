"""リスク管理（損切り/利確・最大DDブレーカー・サイジング）の単体テスト。"""

import pandas as pd

from autotrade.data.base import PriceData
from autotrade.execution.backtest_broker import BacktestBroker
from autotrade.execution.base import CostModel, Portfolio
from autotrade.risk.manager import RiskManager, RiskParams
from autotrade.types import Fill, Order, Side


def _one_symbol_prices(rows):
    df = pd.DataFrame(
        rows, index=pd.date_range("2021-01-01", periods=len(rows))
    )
    return PriceData({"A": df})


def test_drawdown_breaker_halts_and_recovers():
    rm = RiskManager(RiskParams(max_drawdown_pct=0.20))
    assert rm.update_drawdown(100) is False
    assert rm.update_drawdown(120) is False  # 新ピーク
    assert rm.update_drawdown(96) is True     # -20% でブレーカー作動
    assert rm.halted is True
    assert rm.update_drawdown(110) is False    # 回復で解除
    assert rm.halted is False


def test_stop_loss_triggers_exit():
    rm = RiskManager(RiskParams(stop_loss_pct=0.10, take_profit_pct=1.0))
    pf = Portfolio(cash=10_000, currency="JPY")
    broker = BacktestBroker(pf, CostModel(), lot_size=1)

    # 1000円で5株保有 → stop=900。
    broker.execute(Order("A", Side.BUY, 5, "entry"), ref_price=1000, date="d0")
    rm.on_fill(Fill("d0", "A", Side.BUY, 5, 1000, 0.0), pf)
    assert pf.position("A").stop_price == 900

    # 当日安値が 880 → 損切り発動。
    prices = _one_symbol_prices(
        [{"open": 950, "high": 960, "low": 880, "close": 890, "volume": 1}]
    )
    date = prices.dates[0]
    rm.check_stops(pf, prices, date, broker)
    assert pf.position("A").shares == 0
    assert broker.trades[-1].reason == "stop"


def test_take_profit_triggers_exit():
    rm = RiskManager(RiskParams(stop_loss_pct=1.0, take_profit_pct=0.20))
    pf = Portfolio(cash=10_000, currency="JPY")
    broker = BacktestBroker(pf, CostModel(), lot_size=1)

    broker.execute(Order("A", Side.BUY, 5, "entry"), ref_price=1000, date="d0")
    rm.on_fill(Fill("d0", "A", Side.BUY, 5, 1000, 0.0), pf)
    assert pf.position("A").tp_price == 1200

    prices = _one_symbol_prices(
        [{"open": 1100, "high": 1250, "low": 1090, "close": 1240, "volume": 1}]
    )
    rm.check_stops(pf, prices, prices.dates[0], broker)
    assert pf.position("A").shares == 0
    assert broker.trades[-1].reason == "take_profit"


def test_take_profit_can_be_disabled():
    # take_profit_pct=None なら利確線を引かない（勝者を伸ばす設定）。
    rm = RiskManager(RiskParams(stop_loss_pct=0.10, take_profit_pct=None))
    pf = Portfolio(cash=10_000, currency="JPY")
    broker = BacktestBroker(pf, CostModel(), lot_size=1)
    broker.execute(Order("A", Side.BUY, 5, "entry"), ref_price=1000, date="d0")
    rm.on_fill(Fill("d0", "A", Side.BUY, 5, 1000, 0.0), pf)
    assert pf.position("A").tp_price is None

    # +30% まで上がっても利確で売られない（保有継続）。
    prices = _one_symbol_prices(
        [{"open": 1250, "high": 1350, "low": 1240, "close": 1300, "volume": 1}]
    )
    rm.check_stops(pf, prices, prices.dates[0], broker)
    assert pf.position("A").shares == 5


def test_trailing_stop_locks_in_gains():
    # トレーリング20%。最高値から20%下げたら売る（損切り線が高値追随で上がる）。
    rm = RiskManager(
        RiskParams(stop_loss_pct=0.50, take_profit_pct=None, trailing_stop_pct=0.20)
    )
    pf = Portfolio(cash=10_000, currency="JPY")
    broker = BacktestBroker(pf, CostModel(), lot_size=1)
    broker.execute(Order("A", Side.BUY, 5, "entry"), ref_price=1000, date="d0")
    rm.on_fill(Fill("d0", "A", Side.BUY, 5, 1000, 0.0), pf)

    # Day1: 高値2000 まで上昇 → トレーリング線 = 2000*0.8 = 1600 に切り上がる。安値1800では未発動。
    p1 = _one_symbol_prices(
        [{"open": 1500, "high": 2000, "low": 1800, "close": 1900, "volume": 1}]
    )
    rm.check_stops(pf, p1, p1.dates[0], broker)
    assert pf.position("A").shares == 5
    assert pf.position("A").stop_price == 1600  # 取得時の500から高値追随で引き上げ

    # Day2: 安値1550 が 1600 を割る → トレーリングストップ発動で売却（利益確保）。
    p2 = _one_symbol_prices(
        [{"open": 1700, "high": 1750, "low": 1550, "close": 1580, "volume": 1}]
    )
    rm.check_stops(pf, p2, p2.dates[0], broker)
    assert pf.position("A").shares == 0
    assert broker.trades[-1].reason == "stop"


def test_position_sizing_respects_per_symbol_weight():
    rm = RiskManager(RiskParams(per_symbol_max_weight=0.20, max_gross_exposure=1.0))
    pf = Portfolio(cash=10_000, currency="JPY")
    prices = _one_symbol_prices(
        [{"open": 1000, "high": 1010, "low": 990, "close": 1000, "volume": 1}]
    )
    date = prices.dates[0]
    signal = pd.Series({"A": 1})
    orders = rm.build_orders(signal, pf, prices, date, equity=10_000)
    # 目標額 = 10000*0.2 = 2000 → 1000円で2株。
    assert len(orders) == 1
    assert orders[0].side == Side.BUY
    assert orders[0].shares == 2


def test_no_new_entry_when_halted():
    rm = RiskManager(RiskParams())
    rm.halted = True
    pf = Portfolio(cash=10_000, currency="JPY")
    prices = _one_symbol_prices(
        [{"open": 1000, "high": 1010, "low": 990, "close": 1000, "volume": 1}]
    )
    orders = rm.build_orders(pd.Series({"A": 1}), pf, prices, prices.dates[0], 10_000)
    assert orders == []

"""約定シミュレーション（BacktestBroker・CostModel）の単体テスト。"""

from autotrade.execution.backtest_broker import BacktestBroker
from autotrade.execution.base import CostModel, Portfolio
from autotrade.types import Order, Side


def test_slippage_direction():
    cost = CostModel(slippage_bps=100)  # 1%
    assert abs(cost.fill_price(100, Side.BUY) - 101) < 1e-9
    assert abs(cost.fill_price(100, Side.SELL) - 99) < 1e-9


def test_min_commission_applies():
    cost = CostModel(commission_rate=0.001, min_commission=100)
    # 0.1% で計算すると 50 だが、最低手数料 100 が適用される。
    assert cost.commission(50_000) == 100
    assert cost.commission(200_000) == 200


def test_buy_then_sell_updates_cash_and_records_trade():
    pf = Portfolio(cash=10_000, currency="JPY")
    cost = CostModel(commission_rate=0.0, slippage_bps=0.0)
    broker = BacktestBroker(pf, cost, lot_size=1)

    broker.execute(Order("A", Side.BUY, 5, "entry"), ref_price=1000, date="d1")
    pos = pf.position("A")
    assert pos.shares == 5
    assert pf.cash == 10_000 - 5 * 1000

    broker.execute(Order("A", Side.SELL, 5, "exit"), ref_price=1200, date="d2")
    assert pf.position("A").shares == 0
    assert pf.cash == 5_000 + 5 * 1200
    assert len(broker.trades) == 1
    assert abs(broker.trades[0].pnl - (1200 - 1000) * 5) < 1e-9


def test_cannot_buy_more_than_cash():
    pf = Portfolio(cash=1_000, currency="JPY")
    cost = CostModel()
    broker = BacktestBroker(pf, cost, lot_size=1)
    # 1株1000円なので最大1株しか買えない。
    broker.execute(Order("A", Side.BUY, 100, "entry"), ref_price=1000, date="d1")
    assert pf.position("A").shares == 1
    assert pf.cash >= 0


def test_lot_size_rounding():
    pf = Portfolio(cash=1_000_000, currency="JPY")
    cost = CostModel()
    broker = BacktestBroker(pf, cost, lot_size=100)
    broker.execute(Order("A", Side.BUY, 150, "entry"), ref_price=1000, date="d1")
    # 100株単位に丸められる。
    assert pf.position("A").shares == 100

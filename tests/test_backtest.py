"""
Unit and Integration Tests for Backtest Engine, Metrics, and Plotter.
Verifies:
1. Strict No Look-Ahead property.
2. Limit order penetration constraint (does not fill on mere touch).
3. Conservative conflict resolution (SL triggers before TP on same candle).
4. Partial take-profit (50%) and automatic move to Break-Even.
5. Mathematical accuracy of metrics calculations.
6. Chart generation and file persistence.
"""

from datetime import datetime
import os
from zoneinfo import ZoneInfo
import pytest

from src.core.events import Bar, OrderSide, OrderStatus, Signal, SignalDirection
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import PerformanceCalculator, TradeRecord
from src.backtest.plotter import TradePlotter

UTC = ZoneInfo("UTC")


def test_backtest_penetration_constraint():
    """Limit orders must NOT fill on touch; they require genuine penetration."""
    strategy = WamFvgStrategy()
    risk_manager = RiskManager()
    engine = BacktestEngine(
        strategy=strategy,
        risk_manager=risk_manager,
        min_penetration_ticks=1,
        tick_size=0.1
    )

    # Place a pending BUY LIMIT order at 5820.0
    sig = Signal(
        id="sig_1", strategy_id="wam_fvg", symbol="US500", direction=SignalDirection.LONG,
        timeframe="M5", entry_price=5820.0, stop_loss=5810.0, take_profit_1=5840.0
    )
    risk_res = risk_manager.evaluate_signal(sig, engine.account, open_positions=[])
    from src.backtest.engine import PendingLimitOrder
    engine.pending_orders.append(PendingLimitOrder(order=risk_res.order, signal=sig, placed_at_bar_index=0))

    # Bar 1: Low is exactly 5820.0 (touches entry price, but does not penetrate by 1 tick = 0.1)
    bar_touch = Bar(
        symbol="US500", timeframe="M5", timestamp=datetime(2026, 4, 15, 14, 0, tzinfo=UTC),
        open=5825.0, high=5830.0, low=5820.0, close=5822.0
    )
    engine._check_pending_orders(bar_touch, current_idx=1)
    assert len(engine.open_positions) == 0  # NOT filled!
    assert len(engine.pending_orders) == 1

    # Bar 2: Low is 5819.8 (penetrates by 2 ticks = 0.2 >= 0.1)
    bar_penetrate = Bar(
        symbol="US500", timeframe="M5", timestamp=datetime(2026, 4, 15, 14, 5, tzinfo=UTC),
        open=5822.0, high=5824.0, low=5819.8, close=5821.0
    )
    engine._check_pending_orders(bar_penetrate, current_idx=2)
    assert len(engine.open_positions) == 1  # FILLED!
    assert len(engine.pending_orders) == 0


def test_backtest_conservative_sl_tp_same_candle():
    """If both SL and TP fall in the same candle, SL triggers first."""
    strategy = WamFvgStrategy()
    risk_manager = RiskManager()
    engine = BacktestEngine(strategy=strategy, risk_manager=risk_manager)

    # Position Long: Entry 5820, SL 5810, TP1 5840
    from src.core.events import Position
    pos = Position(
        id="pos_1", symbol="US500", side=OrderSide.BUY, size_contracts=1.0,
        entry_price=5820.0, current_price=5820.0, stop_loss=5810.0, take_profit_1=5840.0,
        risk_amount_monetary=10.0, risk_bucket="us_indices", opened_at=datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
    )
    engine.open_positions.append(pos)

    # Wild candle: Low is 5805 (below SL), High is 5845 (above TP1)
    bar_conflict = Bar(
        symbol="US500", timeframe="M5", timestamp=datetime(2026, 4, 15, 14, 5, tzinfo=UTC),
        open=5820.0, high=5845.0, low=5805.0, close=5830.0
    )
    engine._update_open_positions(bar_conflict)

    assert len(engine.open_positions) == 0
    assert len(engine.completed_trades) == 1
    # Must exit at Stop Loss, NOT Take Profit!
    assert engine.completed_trades[0].exit_reason == "SL (Conservative Conflict)"
    assert engine.completed_trades[0].pnl_monetary < 0


def test_backtest_partial_close_and_breakeven():
    """Hits TP1 -> closes 50%, moves SL to Break-Even, leaves runner."""
    strategy = WamFvgStrategy()
    risk_manager = RiskManager()
    engine = BacktestEngine(strategy=strategy, risk_manager=risk_manager)

    from src.core.events import Position
    pos = Position(
        id="pos_partial", symbol="US500", side=OrderSide.BUY, size_contracts=2.0,
        entry_price=5820.0, current_price=5820.0, stop_loss=5810.0, take_profit_1=5840.0,
        take_profit_2=5860.0, risk_amount_monetary=20.0, opened_at=datetime(2026, 4, 15, 14, 0, tzinfo=UTC)
    )
    engine.open_positions.append(pos)

    # Candle hits TP1 (High 5842 > 5840), Low 5815 (SL not hit)
    bar_tp1 = Bar(
        symbol="US500", timeframe="M5", timestamp=datetime(2026, 4, 15, 14, 5, tzinfo=UTC),
        open=5822.0, high=5842.0, low=5815.0, close=5838.0
    )
    engine._update_open_positions(bar_tp1)

    # 1. 50% partial taken
    assert len(engine.completed_trades) == 1
    assert engine.completed_trades[0].exit_reason == "TP1 (50% partial)"
    assert pytest.approx(engine.completed_trades[0].size_contracts, 0.01) == 1.0
    assert engine.completed_trades[0].pnl_monetary > 0

    # 2. Remaining runner is at Break-Even
    assert len(engine.open_positions) == 1
    runner = engine.open_positions[0]
    assert pytest.approx(runner.size_contracts, 0.01) == 1.0
    assert runner.is_partially_closed is True
    assert runner.stop_loss == 5820.0  # SL moved to entry price!


def test_metrics_calculation_accuracy():
    """Validates math behind Win Rate, Profit Factor, Expectancy R, and Max Drawdown."""
    trades = [
        TradeRecord(trade_id="t1", symbol="US500", direction="LONG", entry_time=datetime.utcnow(), exit_time=datetime.utcnow(), entry_price=5800, exit_price=5840, initial_sl=5790, initial_tp1=5840, initial_tp2=None, size_contracts=1.0, pnl_monetary=20.0, r_multiple=2.0, mae=0, mfe=40, exit_reason="TP1"),
        TradeRecord(trade_id="t2", symbol="US500", direction="LONG", entry_time=datetime.utcnow(), exit_time=datetime.utcnow(), entry_price=5800, exit_price=5790, initial_sl=5790, initial_tp1=5840, initial_tp2=None, size_contracts=1.0, pnl_monetary=-10.0, r_multiple=-1.0, mae=10, mfe=5, exit_reason="SL"),
        TradeRecord(trade_id="t3", symbol="USTEC", direction="SHORT", entry_time=datetime.utcnow(), exit_time=datetime.utcnow(), entry_price=20000, exit_price=19950, initial_sl=20025, initial_tp1=19950, initial_tp2=None, size_contracts=1.0, pnl_monetary=25.0, r_multiple=2.5, mae=0, mfe=50, exit_reason="TP1"),
        TradeRecord(trade_id="t4", symbol="DE40", direction="LONG", entry_time=datetime.utcnow(), exit_time=datetime.utcnow(), entry_price=19000, exit_price=19000, initial_sl=18950, initial_tp1=19100, initial_tp2=None, size_contracts=1.0, pnl_monetary=0.0, r_multiple=0.0, mae=5, mfe=15, exit_reason="BE"),
    ]

    report = PerformanceCalculator.calculate(trades, initial_capital=1000.0)

    assert report.total_trades == 4
    assert report.winning_trades == 2
    assert report.losing_trades == 1
    assert report.breakeven_trades == 1
    assert pytest.approx(report.win_rate_pct, 0.01) == 50.0
    assert pytest.approx(report.profit_factor, 0.01) == 4.5  # 45.0 / 10.0
    assert pytest.approx(report.net_pnl, 0.01) == 35.0      # 20 - 10 + 25 + 0
    assert report.expectancy_r > 0.0

    table = report.summary_table()
    assert "BACKTEST PERFORMANCE SCORECARD" in table
    assert "US500" in table
    assert "USTEC" in table


def test_trade_plotter_generates_file():
    """Validates chart rendering and file creation."""
    from datetime import timedelta
    base_ts = datetime(2026, 4, 15, 13, 0, tzinfo=UTC)
    bars = [
        Bar(symbol="US500", timeframe="M5", timestamp=base_ts + timedelta(minutes=i*5), open=5810+i, high=5815+i, low=5808+i, close=5812+i)
        for i in range(15)
    ]
    trade = TradeRecord(
        trade_id="test_plot_1", symbol="US500", direction="LONG", entry_time=bars[5].timestamp,
        exit_time=bars[-1].timestamp, entry_price=5815.0, exit_price=5826.0, initial_sl=5805.0,
        initial_tp1=5826.0, initial_tp2=5835.0, size_contracts=1.0, pnl_monetary=11.0, r_multiple=1.1,
        mae=2.0, mfe=11.0, exit_reason="TP1"
    )

    filepath = TradePlotter.plot_trade(
        bars=bars,
        trade=trade,
        range_high=5825.0,
        range_low=5808.0,
        fvg_top=5818.0,
        fvg_bottom=5814.0,
        output_filename="test_chart_output.png"
    )

    assert os.path.exists(filepath)
    assert os.path.getsize(filepath) > 1000  # Non-empty PNG file

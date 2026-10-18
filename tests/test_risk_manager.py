"""
Unit tests for Central RiskManager.
Verifies all non-negotiable risk rules:
1. 1% max risk per trade.
2. 3% max daily drawdown circuit breaker.
3. Max 3 concurrent open positions.
4. Correlation bucket constraint (us_indices max 1 open position).
5. Mandatory Stop Loss and accurate contract sizing.
"""

import pytest
from datetime import datetime

from src.core.events import (
    AccountInfo,
    OrderSide,
    OrderStatus,
    Position,
    Signal,
    SignalDirection,
)
from src.risk.manager import RiskManager, InstrumentSpec


def create_sample_signal(
    symbol: str = "US500",
    entry: float = 5850.0,
    sl: float = 5840.0,
    tp1: float = 5880.0,
    bucket: str = "us_indices"
) -> Signal:
    return Signal(
        id="sig_test_1",
        strategy_id="wam_fvg",
        symbol=symbol,
        direction=SignalDirection.LONG,
        timeframe="M5",
        entry_price=entry,
        stop_loss=sl,
        take_profit_1=tp1,
        confidence_score=75.0,
        risk_bucket=bucket,
        rationale="Test spring signal"
    )


def test_risk_manager_sizing_and_approval():
    rm = RiskManager(
        max_risk_per_trade_pct=1.0,
        max_daily_drawdown_pct=3.0,
        max_open_positions=3,
        min_risk_reward_ratio=2.0
    )
    account = AccountInfo(balance=1000.0, equity=1000.0, daily_starting_equity=1000.0)
    signal = create_sample_signal(entry=5850.0, sl=5840.0, tp1=5880.0)  # Stop distance = 10 points

    # On €1,000 equity, 1% risk = €10.00
    # Stop distance = 10 pts, point value = 1.0 -> Size = 10 / 10 = 1.0 contract
    res = rm.evaluate_signal(signal, account, open_positions=[])

    assert res.approved is True
    assert res.order is not None
    assert res.order.status == OrderStatus.APPROVED
    assert pytest.approx(res.order.size_contracts, 0.01) == 1.0
    assert pytest.approx(res.order.risk_amount_monetary, 0.01) == 10.0
    assert pytest.approx(res.order.risk_percentage, 0.01) == 1.0


def test_risk_manager_rejects_missing_stop_loss():
    rm = RiskManager()
    account = AccountInfo(balance=1000.0, equity=1000.0)
    # Stop loss equal to entry or zero
    signal = create_sample_signal(entry=5850.0, sl=5850.0)

    res = rm.evaluate_signal(signal, account, open_positions=[])
    assert res.approved is False
    assert "Stop Loss is missing or invalid" in (res.rejection_reason or "")


def test_risk_manager_circuit_breaker_3pct():
    rm = RiskManager(max_daily_drawdown_pct=3.0)
    # Account has already lost €35 today (3.5% loss on starting €1,000)
    account = AccountInfo(
        balance=965.0,
        equity=965.0,
        daily_starting_equity=1000.0,
        daily_realized_pnl=-35.0
    )
    signal = create_sample_signal()

    res = rm.evaluate_signal(signal, account, open_positions=[])
    assert res.approved is False
    assert "Daily drawdown limit reached" in (res.rejection_reason or "")


def test_risk_manager_max_3_positions():
    rm = RiskManager(max_open_positions=3)
    account = AccountInfo(balance=1000.0, equity=1000.0)
    # Create 3 dummy open positions
    open_pos = [
        Position(id="p1", symbol="DE40", side=OrderSide.BUY, size_contracts=1.0, entry_price=19000, current_price=19010, stop_loss=18950, take_profit_1=19100, risk_bucket="eu_indices"),
        Position(id="p2", symbol="GOLD", side=OrderSide.BUY, size_contracts=1.0, entry_price=2600, current_price=2605, stop_loss=2590, take_profit_1=2630, risk_bucket="commodities"),
        Position(id="p3", symbol="OIL", side=OrderSide.BUY, size_contracts=1.0, entry_price=70, current_price=71, stop_loss=69, take_profit_1=73, risk_bucket="energy"),
    ]
    signal = create_sample_signal(symbol="US500")

    res = rm.evaluate_signal(signal, account, open_positions=open_pos)
    assert res.approved is False
    assert "Max open positions limit reached" in (res.rejection_reason or "")


def test_risk_manager_correlation_bucket_us_indices():
    rm = RiskManager(one_position_per_bucket=True)
    account = AccountInfo(balance=1000.0, equity=1000.0)
    # Already an open position on US500 in bucket 'us_indices'
    open_pos = [
        Position(id="p1", symbol="US500", side=OrderSide.BUY, size_contracts=1.0, entry_price=5800, current_price=5810, stop_loss=5790, take_profit_1=5840, risk_bucket="us_indices")
    ]
    # New signal for USTEC (also in 'us_indices')
    signal_ustec = create_sample_signal(symbol="USTEC", entry=20400, sl=20350, tp1=20550, bucket="us_indices")

    res = rm.evaluate_signal(signal_ustec, account, open_positions=open_pos)
    assert res.approved is False
    assert "Correlation bucket 'us_indices' already has an open position" in (res.rejection_reason or "")


def test_risk_manager_kill_switch():
    rm = RiskManager(kill_switch_active=True)
    account = AccountInfo(balance=1000.0, equity=1000.0)
    signal = create_sample_signal()

    res = rm.evaluate_signal(signal, account, open_positions=[])
    assert res.approved is False
    assert "Global Kill-Switch is active" in (res.rejection_reason or "")

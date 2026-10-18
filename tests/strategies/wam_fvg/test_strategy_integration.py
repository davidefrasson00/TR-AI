"""
End-to-end Integration test for WamFvgStrategy and RiskManager.
Simulates incremental bar ingestion (no look-ahead), validates signal generation,
and verifies seamless approval and sizing by the Central Risk Manager.
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo
import pytest

from src.core.events import (
    AccountInfo,
    Bar,
    OrderStatus,
    Signal,
    SignalDirection,
)
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.strategies.wam_fvg.fsm import WAMState

UTC = ZoneInfo("UTC")


def test_strategy_end_to_end_flow_and_risk_approval():
    strategy = WamFvgStrategy()
    risk_manager = RiskManager(
        max_risk_per_trade_pct=1.0,
        max_daily_drawdown_pct=3.0,
        max_open_positions=3
    )
    account = AccountInfo(balance=1000.0, equity=1000.0)

    # Date: 2026-04-15 (Standard US Open 09:30 ET = 13:30 UTC)
    # Range Window: 06:30 - 09:30 ET (10:30 - 13:30 UTC)
    bars: list[Bar] = []

    # 1. Generate 12 range bars (M15) between 10:30 UTC and 13:15 UTC oscillating between 5810 and 5835
    for i in range(12):
        hour = 10 + (i * 15 // 60)
        minute = (i * 15) % 60
        ts = datetime(2026, 4, 15, hour, minute, tzinfo=UTC)
        close_p = 5822.0 + (5.0 if i % 2 == 0 else -5.0)
        bars.append(Bar(
            symbol="US500",
            timeframe="M15",
            timestamp=ts,
            open=5820.0,
            high=5835.0,
            low=5810.0,
            close=close_p,
            volume=500.0
        ))

    # Feed range bars to strategy
    for b in bars:
        sig = strategy.on_bar(b)
        assert sig is None

    # Check FSM transitioned to RANGE_BUILDING
    fsm = strategy._get_fsm("US500")
    assert fsm.current_state == WAMState.RANGE_BUILDING

    # 2. Bar at 13:30 UTC (09:30 ET - boundary): triggers evaluation to RANGE_VALID
    bar_eval = Bar(
        symbol="US500",
        timeframe="M5",
        timestamp=datetime(2026, 4, 15, 13, 30, tzinfo=UTC),
        open=5820.0, high=5830.0, low=5815.0, close=5822.0, volume=800.0
    )
    sig = strategy.on_bar(bar_eval)
    assert sig is None
    assert fsm.current_state == WAMState.RANGE_VALID
    assert fsm.context.range_result is not None
    assert fsm.context.range_result.high == 5835.0
    assert fsm.context.range_result.low == 5810.0

    # 3. Sweep bar at 13:35 UTC (09:35 ET): pierces below 5810 to 5805 (depth=5 -> 0.20), closes back at 5814
    bar_sweep = Bar(
        symbol="US500",
        timeframe="M5",
        timestamp=datetime(2026, 4, 15, 13, 35, tzinfo=UTC),
        open=5818.0, high=5820.0, low=5805.0, close=5814.0, volume=1200.0
    )
    sig = strategy.on_bar(bar_sweep)
    assert sig is None
    assert fsm.current_state == WAMState.SWEEP_DETECTED
    assert fsm.context.sweep_result.sweep_extreme == 5805.0

    # 4. Displacement bar at 13:40 UTC: strong green candle up to 5834 with body=26 >= 1.0x ATR
    bar_disp = Bar(
        symbol="US500",
        timeframe="M5",
        timestamp=datetime(2026, 4, 15, 13, 40, tzinfo=UTC),
        open=5806.0, high=5834.0, low=5805.0, close=5832.0, volume=1500.0
    )
    sig = strategy.on_bar(bar_disp)
    assert sig is None
    assert fsm.current_state in [WAMState.DISPLACEMENT_CONFIRMED, WAMState.AWAIT_RETEST]

    # 5. Bar at 13:45 UTC (Retest evaluation): triggers Signal Generation
    bar_signal = Bar(
        symbol="US500",
        timeframe="M5",
        timestamp=datetime(2026, 4, 15, 13, 45, tzinfo=UTC),
        open=5832.0, high=5833.0, low=5820.0, close=5825.0, volume=800.0
    )
    signal = strategy.on_bar(bar_signal)

    # Verify Signal characteristics
    assert signal is not None
    assert signal.symbol == "US500"
    assert signal.direction == SignalDirection.LONG
    assert signal.confidence_score >= 60.0
    # Stop Loss must be at or below sweep extreme (5805) with buffer
    assert signal.stop_loss < 5805.0
    # TP1 must be opposite range extreme (5835) + offset (+2 ticks = +0.2 -> 5835.2)
    assert signal.take_profit_1 > 5835.0
    assert signal.risk_reward_ratio >= 1.0

    # 6. Pass Signal to Central RiskManager
    risk_result = risk_manager.evaluate_signal(signal, account, open_positions=[])

    assert risk_result.approved is True
    assert risk_result.order is not None
    assert risk_result.order.status == OrderStatus.APPROVED
    assert risk_result.risk_percentage <= 1.0
    assert risk_result.risk_amount_monetary <= 10.0
    assert risk_result.calculated_size > 0.0

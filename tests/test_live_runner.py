"""
Unit tests for LivePaperRunner forward-testing engine.
Tests market hours detection, limit order fills, TP1 partial + break-even,
SL exits, and Telegram notification dispatch.
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.events import Bar, Order, OrderSide, OrderType, Position, Signal, SignalDirection
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.bot.telegram_bot import TelegramBot
from src.execution.live_runner import LivePaperRunner
from src.monitoring.api import live_state

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")


@pytest.fixture
def clean_live_state():
    live_state["open_positions"] = []
    live_state["kill_switch_active"] = False
    live_state["account"].balance = 1000.0
    live_state["account"].equity = 1000.0
    live_state["account"].daily_realized_pnl = 0.0
    return live_state


def test_market_hours_check():
    strategy = WamFvgStrategy(strategy_id="wam_fvg")
    rm = RiskManager()
    runner = LivePaperRunner(strategy=strategy, risk_manager=rm)

    # Saturday: Closed
    sat_dt = datetime(2026, 10, 17, 12, 0, tzinfo=ET)
    assert runner.is_market_open(sat_dt) is False

    # Sunday before 18:00 ET: Closed
    sun_early = datetime(2026, 10, 18, 14, 0, tzinfo=ET)
    assert runner.is_market_open(sun_early) is False

    # Sunday after 18:00 ET: Open (continuous futures session starts)
    sun_open = datetime(2026, 10, 18, 19, 0, tzinfo=ET)
    assert runner.is_market_open(sun_open) is True

    # Tuesday during US session: Open
    tue_dt = datetime(2026, 10, 20, 10, 30, tzinfo=ET)
    assert runner.is_market_open(tue_dt) is True


@pytest.mark.anyio
async def test_live_runner_pending_order_fill_and_tp1_breakeven(clean_live_state):
    strategy = WamFvgStrategy(strategy_id="wam_fvg")
    rm = RiskManager()
    bot = TelegramBot(token="")
    runner = LivePaperRunner(strategy=strategy, risk_manager=rm, telegram_bot=bot)

    # Place a pending BUY limit order at 5800.0 (SL 5780, TP1 5830)
    order = Order(
        id="test_ord_1",
        signal_id="sig_test_1",
        symbol="US500",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size_contracts=1.0,
        requested_price=5800.0,
        stop_loss=5780.0,
        take_profit=5830.0,
        take_profit_2=5860.0,
        risk_amount_monetary=10.0,
        risk_percentage=1.0
    )
    runner.pending_orders.append({
        "order": order,
        "signal": None,
        "placed_at": datetime(2026, 10, 19, 13, 30, tzinfo=UTC),
        "expiry_bars": 12,
        "elapsed_bars": 0
    })

    # Bar 1: Price touches 5798 (penetrates 5800) -> Order filled!
    bar_fill = Bar(
        symbol="US500",
        timeframe="5m",
        timestamp=datetime(2026, 10, 19, 13, 35, tzinfo=UTC),
        open=5805.0,
        high=5806.0,
        low=5798.0,
        close=5802.0
    )
    await runner._check_pending_orders(bar_fill)
    assert len(runner.pending_orders) == 0
    assert len(clean_live_state["open_positions"]) == 1
    pos: Position = clean_live_state["open_positions"][0]
    assert pos.symbol == "US500"
    assert pos.entry_price == 5800.0
    assert pos.size_contracts == 1.0

    # Bar 2: Price pushes up to 5835 (hits TP1 at 5830) -> 50% partial close + Move to BE
    bar_tp1 = Bar(
        symbol="US500",
        timeframe="5m",
        timestamp=datetime(2026, 10, 19, 13, 40, tzinfo=UTC),
        open=5810.0,
        high=5835.0,
        low=5808.0,
        close=5832.0
    )
    await runner._check_open_positions(bar_tp1)
    assert len(clean_live_state["open_positions"]) == 1
    pos = clean_live_state["open_positions"][0]
    assert pos.is_partially_closed is True
    assert pos.is_at_breakeven is True
    assert pos.size_contracts == 0.5
    assert pos.stop_loss == 5800.0  # SL at BE!
    assert clean_live_state["account"].daily_realized_pnl == 15.0  # 0.5 contracts * 30 pts = €15.00


@pytest.mark.anyio
async def test_live_runner_sl_exit(clean_live_state):
    strategy = WamFvgStrategy(strategy_id="wam_fvg")
    rm = RiskManager()
    bot = TelegramBot(token="")
    runner = LivePaperRunner(strategy=strategy, risk_manager=rm, telegram_bot=bot)

    # Directly add active position
    pos = Position(
        id="pos_sl_test",
        symbol="USTEC",
        side=OrderSide.BUY,
        size_contracts=0.2,
        entry_price=20000.0,
        current_price=20000.0,
        stop_loss=19950.0,
        take_profit_1=20100.0,
        risk_amount_monetary=10.0,
        risk_bucket="us_indices"
    )
    clean_live_state["open_positions"].append(pos)

    # Bar hits SL at 19940 (< 19950)
    bar_sl = Bar(
        symbol="USTEC",
        timeframe="5m",
        timestamp=datetime(2026, 10, 19, 14, 0, tzinfo=UTC),
        open=19980.0,
        high=19985.0,
        low=19940.0,
        close=19945.0
    )
    await runner._check_open_positions(bar_sl)
    # Position closed!
    assert len(clean_live_state["open_positions"]) == 0
    assert clean_live_state["account"].daily_realized_pnl == -10.0  # 0.2 * 50 pts = -€10.00

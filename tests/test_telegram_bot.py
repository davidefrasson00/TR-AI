"""
Unit tests for TR-AI Telegram Bot.
Tests mock notifications, specialized alerts, interactive command dispatcher,
and security access control.
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from src.core.events import AccountInfo, Position, Signal, SignalDirection, OrderSide
from src.bot.telegram_bot import TelegramBot

UTC = ZoneInfo("UTC")


@pytest.fixture
def mock_live_state():
    return {
        "account": AccountInfo(
            currency="EUR",
            balance=1000.0,
            equity=1024.10,
            daily_starting_equity=1000.0,
            daily_realized_pnl=24.10,
            daily_unrealized_pnl=0.0
        ),
        "open_positions": [
            Position(
                id="pos_test_1",
                symbol="US500",
                side=OrderSide.BUY,
                size_contracts=1.5,
                entry_price=5800.0,
                current_price=5810.0,
                stop_loss=5780.0,
                take_profit_1=5830.0,
                take_profit_2=5860.0,
                risk_amount_monetary=10.0,
                risk_bucket="us_indices",
                unrealized_pnl=15.0
            )
        ],
        "kill_switch_active": False,
        "strategy_name": "WAM-FVG Intraday",
        "strategy_mode": "PAPER TRADING / DEMO"
    }


@pytest.mark.anyio
async def test_telegram_bot_mock_mode_initialization():
    bot = TelegramBot(token="", chat_id="12345678")
    assert bot.is_mock is True
    res = await bot.send_message("Test message")
    assert res is True
    assert len(bot.mock_sent_messages) == 1
    assert "Test message" in bot.mock_sent_messages[0]["text"]


@pytest.mark.anyio
async def test_telegram_notify_signal():
    bot = TelegramBot(token="")
    sig = Signal(
        id="sig_1",
        strategy_id="wam_fvg",
        symbol="US500",
        direction=SignalDirection.LONG,
        timeframe="5m",
        entry_price=5800.0,
        stop_loss=5780.0,
        take_profit_1=5830.0,
        confidence_score=88.5,
        risk_bucket="us_indices",
        created_at=datetime(2026, 10, 15, 13, 45, tzinfo=UTC)
    )

    # Approved signal
    res_app = await bot.notify_signal(sig, approved=True, reason="Valid setup", score=88.5)
    assert res_app is True
    last_msg = bot.mock_sent_messages[-1]["text"]
    assert "APPROVATO DAL RISK MANAGER" in last_msg
    assert "88.5/100" in last_msg
    assert "5800.00" in last_msg

    # Rejected signal
    res_rej = await bot.notify_signal(sig, approved=False, reason="R:R insufficient", score=72.0)
    assert res_rej is True
    assert "RESPINTO DAL RISK MANAGER" in bot.mock_sent_messages[-1]["text"]


@pytest.mark.anyio
async def test_telegram_notify_trade_events():
    bot = TelegramBot(token="")
    pos = Position(
        id="pos_live_123",
        symbol="USTEC",
        side=OrderSide.BUY,
        size_contracts=0.5,
        entry_price=20000.0,
        current_price=20050.0,
        stop_loss=19950.0,
        take_profit_1=20100.0,
        risk_amount_monetary=10.0,
        risk_bucket="us_indices"
    )

    # Trade opened
    await bot.notify_trade_opened(pos)
    assert "OPERAZIONE APERTA" in bot.mock_sent_messages[-1]["text"]

    # TP1 hit
    await bot.notify_trade_tp1(pos, pnl=25.0, r_mult=2.5)
    assert "TARGET TP1 RAGGIUNTO" in bot.mock_sent_messages[-1]["text"]
    assert "BREAK-EVEN" in bot.mock_sent_messages[-1]["text"]

    # Full trade closed
    await bot.notify_trade_closed(pos, pnl=25.0, r_mult=2.5, reason="TP2 (Runner)")
    assert "OPERAZIONE COMPLETATA" in bot.mock_sent_messages[-1]["text"]

    # Circuit breaker
    await bot.notify_circuit_breaker(dd_pct=3.15)
    assert "CIRCUIT BREAKER" in bot.mock_sent_messages[-1]["text"]


@pytest.mark.anyio
async def test_telegram_interactive_commands(mock_live_state):
    bot = TelegramBot(token="", chat_id="999", live_state=mock_live_state)

    # /status
    status_resp = await bot.handle_command("/status", [], sender_id="999")
    assert "STATO DI SISTEMA" in status_resp
    assert "US500" in status_resp or "Equity" in status_resp

    # /positions
    pos_resp = await bot.handle_command("/positions", [], sender_id="999")
    assert "POSIZIONI APERTE" in pos_resp
    assert "US500" in pos_resp

    # /kill
    kill_resp = await bot.handle_command("/kill", [], sender_id="999")
    assert "KILL SWITCH ATTIVATO" in kill_resp
    assert mock_live_state["kill_switch_active"] is True

    # /resume
    resume_resp = await bot.handle_command("/resume", [], sender_id="999")
    assert "KILL SWITCH DISATTIVATO" in resume_resp
    assert mock_live_state["kill_switch_active"] is False

    # /help
    help_resp = await bot.handle_command("/help", [], sender_id="999")
    assert "/kill" in help_resp


@pytest.mark.anyio
async def test_telegram_security_unauthorized_user(mock_live_state):
    bot = TelegramBot(token="", chat_id="999", live_state=mock_live_state)
    # Unauthorized sender
    resp = await bot.handle_command("/kill", [], sender_id="intruder_123")
    assert "Accesso Negato" in resp
    assert mock_live_state["kill_switch_active"] is False  # Must NOT be modified

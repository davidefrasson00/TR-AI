"""
TR-AI — Live Paper Trading & Telegram Execution Daemon.
Runs the live forward-testing engine in continuous background mode:
- Polls live candles from markets as they form.
- Evaluates strategy signals and enforces central risk management.
- Dispatches instant notifications and accepts interactive commands via Telegram.
- Synchronizes with Glassmorphism dashboard on http://localhost:8000.
"""

import asyncio
import os
import signal
import sys
from typing import List

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.logger import decision_logger
from src.bot.telegram_bot import TelegramBot
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.execution.live_runner import LivePaperRunner
from src.monitoring.api import live_state


async def main():
    print("=" * 70)
    print("🤖 TR-AI — LIVE PAPER TRADING & TELEGRAM RUNNER")
    print("=" * 70)

    # 1. Initialize Strategy & Risk Manager
    strategy = WamFvgStrategy(
        strategy_id="wam_fvg",
        buffer_ticks=2,
        tp1_offset_ticks=2,
        min_score=60.0
    )

    risk_manager = RiskManager(
        max_risk_per_trade_pct=1.0,
        max_daily_drawdown_pct=3.0,
        max_open_positions=3,
        one_position_per_bucket=True
    )

    # 2. Initialize Telegram Bot
    telegram_bot = TelegramBot(
        live_state=live_state,
        on_kill_switch=lambda active, reason: decision_logger.log_decision(
            "KILL_SWITCH", "ALL", "ACTIVATED" if active else "DEACTIVATED", reason
        )
    )

    # Start Telegram background polling
    telegram_bot.start()

    # 3. Initialize Live Paper Runner
    runner = LivePaperRunner(
        strategy=strategy,
        risk_manager=risk_manager,
        telegram_bot=telegram_bot,
        symbols=["US500", "USTEC", "DE40"],
        poll_interval_seconds=15
    )

    # Handle graceful termination
    loop = asyncio.get_running_loop()

    def shutdown():
        print("\nInitiating graceful shutdown...")
        runner.stop()
        telegram_bot.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except NotImplementedError:
            pass

    # Status banner
    is_open = runner.is_market_open()
    status_str = "🟢 MARKETS OPEN (Active Forward Testing)" if is_open else "🟡 MARKETS CLOSED (Waiting for session open)"
    print(f"\nStatus: {status_str}")
    print(f"Monitoring: US500 (ES=F), USTEC (NQ=F), DE40 (^GDAXI)")
    print(f"Web Dashboard: http://localhost:8000")
    print(f"Telegram Bot: {'MOCK MODE (set TELEGRAM_BOT_TOKEN in .env)' if telegram_bot.is_mock else 'CONNECTED'}")
    print("\nPress CTRL+C to stop.\n")

    # Send startup message via Telegram
    await telegram_bot.send_message(
        f"🤖 <b>TR-AI Live Engine Avviato!</b>\n\n"
        f"<b>Stato Mercato:</b> {'APERTO' if is_open else 'CHIUSO (in attesa di apertura sessione)'}\n"
        f"<b>Modalità:</b> PAPER TRADING / SIMULAZIONE\n"
        f"<b>Dashboard:</b> http://localhost:8000\n"
        f"Usa /status per controllare il conto."
    )

    await runner.run_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTR-AI Live Engine stopped by user.")

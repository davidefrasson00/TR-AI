"""
Live Paper Trading Runner for TR-AI.
Executes real-time forward paper trading:
1. Checks market session hours (handles market open/close cycles).
2. Polls/receives latest completed 5-minute bars for configured symbols (US500, USTEC, DE40).
3. Evaluates WamFvgStrategy and passes signals through RiskManager.
4. Simulates paper fills, partial TP1 (50%) + Break-Even move, and runner exits.
5. Synchronizes in real-time with FastAPI live_state and pushes mobile alerts via TelegramBot.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from src.core.events import (
    AccountInfo,
    Bar,
    Order,
    OrderSide,
    OrderStatus,
    Position,
    Signal,
    SignalDirection,
)
from src.core.logger import decision_logger
from src.data.yfinance_provider import YFinanceProvider
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.bot.telegram_bot import TelegramBot

UTC = ZoneInfo("UTC")


class LivePaperRunner:
    """
    Continuous forward-testing paper engine.
    Monitors live markets, runs FSM strategy, and routes alerts to Telegram.
    """

    def __init__(
        self,
        strategy: WamFvgStrategy,
        risk_manager: RiskManager,
        live_state: Optional[Dict] = None,
        telegram_bot: Optional[TelegramBot] = None,
        symbols: Optional[List[str]] = None,
        poll_interval_seconds: int = 15,
        tick_size: float = 0.1,
        point_value: float = 1.0,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.live_state = live_state if live_state is not None else {
            "account": AccountInfo(currency="EUR", balance=1000.0, equity=1000.0, daily_starting_equity=1000.0),
            "open_positions": [],
            "kill_switch_active": False,
            "strategy_mode": "PAPER TRADING / LIVE DEMO"
        }
        self.telegram_bot = telegram_bot
        self.symbols = symbols or ["US500", "USTEC", "DE40"]
        self.poll_interval = poll_interval_seconds
        self.tick_size = tick_size
        self.point_value = point_value

        self.data_provider = YFinanceProvider(use_cache=False)
        self.last_processed_timestamps: Dict[str, datetime] = {}
        self.pending_orders: List[Dict] = []
        self._is_running = False
        self._runner_task: Optional[asyncio.Task] = None

    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Checks if global index CFD / futures markets are actively trading.
        Continuous futures (ES, NQ) trade Sunday 18:00 ET to Friday 17:00 ET.
        """
        now = dt or datetime.now(ZoneInfo("America/New_York"))
        # Saturday: completely closed
        if now.weekday() == 5:
            return False
        # Sunday: opens at 18:00 ET
        if now.weekday() == 6 and now.hour < 18:
            return False
        # Friday: closes at 17:00 ET
        if now.weekday() == 4 and now.hour >= 17:
            return False
        return True

    async def step(self) -> None:
        """Single polling evaluation iteration across all instruments."""
        # 1. Kill Switch Check
        if self.live_state.get("kill_switch_active", False):
            return

        now_utc = datetime.now(UTC)
        is_open = self.is_market_open()

        if not is_open:
            # Market currently closed (weekend or maintenance)
            self.live_state["strategy_mode"] = "PAPER TRADING (MARKET CLOSED • WAITING FOR OPEN)"
            return
        else:
            self.live_state["strategy_mode"] = "PAPER TRADING / LIVE DEMO"

        # 2. Fetch latest candles for each symbol
        for symbol in self.symbols:
            try:
                # Fetch recent 5m bars without cache to capture latest market data
                bars = self.data_provider.get_bars(symbol, timeframe="5m", period="2d")
                if not bars:
                    continue

                latest_bar = bars[-1]
                last_ts = self.last_processed_timestamps.get(symbol)

                # Process only new completed candles
                if last_ts is None or latest_bar.timestamp > last_ts:
                    self.last_processed_timestamps[symbol] = latest_bar.timestamp
                    await self._on_new_bar(latest_bar)

            except Exception as e:
                decision_logger.error(f"LivePaperRunner error polling {symbol}: {e}")

    async def _on_new_bar(self, bar: Bar) -> None:
        """Handles a newly arrived 5-minute candle."""
        # 1. Check pending limit orders against this new bar
        await self._check_pending_orders(bar)

        # 2. Update existing open positions (SL/TP1/TP2 checks)
        await self._check_open_positions(bar)

        # 3. Strategy evaluation
        signal = self.strategy.on_bar(bar)
        if signal:
            # Evaluate with RiskManager
            account = self.live_state["account"]
            current_positions = self.live_state["open_positions"]
            risk_decision = self.risk_manager.evaluate_signal(
                signal=signal,
                account=account,
                open_positions=current_positions,
                tick_size=self.tick_size
            )

            # Push alert to Telegram
            if self.telegram_bot:
                await self.telegram_bot.notify_signal(
                    signal=signal,
                    approved=risk_decision.approved,
                    reason=risk_decision.rejection_reason or "Risk filters passed",
                    score=signal.confidence_score
                )

            if risk_decision.approved and risk_decision.order:
                # Arm pending paper order
                self.pending_orders.append({
                    "order": risk_decision.order,
                    "signal": signal,
                    "placed_at": bar.timestamp,
                    "expiry_bars": 12,
                    "elapsed_bars": 0
                })
                decision_logger.log_decision(
                    "LIVE_PAPER", bar.symbol, "ORDER_PENDING",
                    f"Limit order armed at {risk_decision.order.requested_price:.2f}"
                )

    async def _check_pending_orders(self, bar: Bar) -> None:
        """Checks if price penetrated limit price."""
        remaining_pending = []
        for p_order in self.pending_orders:
            order: Order = p_order["order"]
            if order.symbol != bar.symbol:
                remaining_pending.append(p_order)
                continue

            p_order["elapsed_bars"] += 1
            if p_order["elapsed_bars"] > p_order["expiry_bars"]:
                decision_logger.log_decision("LIVE_PAPER", bar.symbol, "ORDER_EXPIRED", "Pending limit order expired")
                continue

            filled = False
            fill_price = order.requested_price

            # Penetration check
            if order.side == OrderSide.BUY:
                if bar.low <= order.requested_price:
                    filled = True
            elif order.side == OrderSide.SELL:
                if bar.high >= order.requested_price:
                    filled = True

            if filled:
                pos = Position(
                    id=f"pos_{order.id}",
                    symbol=order.symbol,
                    side=order.side,
                    size_contracts=order.size_contracts,
                    entry_price=fill_price,
                    current_price=bar.close,
                    stop_loss=order.stop_loss,
                    take_profit_1=order.take_profit,
                    take_profit_2=order.take_profit_2,
                    risk_amount_monetary=order.risk_amount_monetary,
                    risk_bucket=p_order["signal"].risk_bucket if p_order.get("signal") else "default",
                    unrealized_pnl=0.0,
                    opened_at=bar.timestamp
                )
                self.live_state["open_positions"].append(pos)
                decision_logger.log_decision(
                    "LIVE_PAPER", bar.symbol, "FILLED",
                    f"Filled {pos.size_contracts} at {fill_price:.2f}"
                )
                if self.telegram_bot:
                    await self.telegram_bot.notify_trade_opened(pos)
            else:
                remaining_pending.append(p_order)

        self.pending_orders = remaining_pending

    async def _check_open_positions(self, bar: Bar) -> None:
        """Updates trailing excursions and executes SL / TP1 / TP2."""
        remaining = []
        for pos in self.live_state["open_positions"]:
            if pos.symbol != bar.symbol:
                remaining.append(pos)
                continue

            is_long = pos.side == OrderSide.BUY
            pos.current_price = bar.close
            pnl_pts = (bar.close - pos.entry_price) if is_long else (pos.entry_price - bar.close)
            pos.unrealized_pnl = round(pos.size_contracts * pnl_pts * self.point_value, 2)

            sl_hit = (bar.low <= pos.stop_loss) if is_long else (bar.high >= pos.stop_loss)
            tp1_hit = (bar.high >= pos.take_profit_1) if is_long else (bar.low <= pos.take_profit_1)

            # Conservative Conflict check
            if sl_hit and tp1_hit:
                # Stop loss takes precedence
                await self._close_trade(pos, exit_price=pos.stop_loss, reason="SL (Conservative Conflict)")
                continue

            if sl_hit:
                await self._close_trade(pos, exit_price=pos.stop_loss, reason="SL")
                continue

            # TP1 partial close & Break-Even
            if tp1_hit and not pos.is_partially_closed:
                partial_size = round(pos.size_contracts * 0.5, 4)
                pnl_pts_tp1 = (pos.take_profit_1 - pos.entry_price) if is_long else (pos.entry_price - pos.take_profit_1)
                pnl_monetary = partial_size * pnl_pts_tp1 * self.point_value
                r_mult = pnl_monetary / (pos.risk_amount_monetary * 0.5)

                # Move Stop Loss to Break-Even
                pos.size_contracts = round(pos.size_contracts - partial_size, 4)
                pos.stop_loss = pos.entry_price
                pos.is_partially_closed = True
                pos.is_at_breakeven = True

                acc: AccountInfo = self.live_state["account"]
                acc.balance += pnl_monetary
                acc.equity += pnl_monetary
                acc.daily_realized_pnl += pnl_monetary

                if self.telegram_bot:
                    await self.telegram_bot.notify_trade_tp1(pos, pnl=pnl_monetary, r_mult=r_mult)

                remaining.append(pos)
                continue

            # TP2 on Runner
            if pos.is_partially_closed and pos.take_profit_2:
                tp2_hit = (bar.high >= pos.take_profit_2) if is_long else (bar.low <= pos.take_profit_2)
                if tp2_hit:
                    await self._close_trade(pos, exit_price=pos.take_profit_2, reason="TP2 (Runner)")
                    continue

            remaining.append(pos)

        self.live_state["open_positions"] = remaining

    async def _close_trade(self, pos: Position, exit_price: float, reason: str) -> None:
        """Closes a position and records realized P&L."""
        is_long = pos.side == OrderSide.BUY
        pnl_pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
        pnl_monetary = round(pos.size_contracts * pnl_pts * self.point_value, 2)
        initial_risk = pos.risk_amount_monetary * (0.5 if pos.is_partially_closed else 1.0)
        r_mult = round(pnl_monetary / initial_risk, 2) if initial_risk > 0 else 0.0

        acc: AccountInfo = self.live_state["account"]
        acc.balance += pnl_monetary
        acc.equity += pnl_monetary
        acc.daily_realized_pnl += pnl_monetary

        decision_logger.log_decision(
            "LIVE_PAPER_EXIT", pos.symbol, reason,
            f"Closed trade with PnL: €{pnl_monetary:+.2f} ({r_mult:+.2f}R)"
        )

        if self.telegram_bot:
            await self.telegram_bot.notify_trade_closed(pos, pnl=pnl_monetary, r_mult=r_mult, reason=reason)

        # Check circuit breaker
        if acc.daily_drawdown_pct >= 3.0:
            if self.telegram_bot:
                await self.telegram_bot.notify_circuit_breaker(acc.daily_drawdown_pct)

    async def run_forever(self) -> None:
        """Continuous polling background loop."""
        self._is_running = True
        decision_logger.info("LivePaperRunner started. Listening to market feeds...")
        while self._is_running:
            try:
                await self.step()
            except Exception as e:
                decision_logger.error(f"Error in LivePaperRunner loop: {e}")
            await asyncio.sleep(self.poll_interval)

    def stop(self) -> None:
        self._is_running = False
        if self._runner_task and not self._runner_task.done():
            self._runner_task.cancel()

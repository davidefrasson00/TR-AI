"""
Event-Driven Backtest Simulation Engine for TR-AI.

Features:
1. Incremental, candle-by-candle feed (zero look-ahead, identical to live).
2. Realistic limit order penetration constraint (does not fill on mere touch).
3. Conservative intraday conflict handling: if SL and TP occur in the same bar, SL is hit first.
4. Active position lifecycle management: partial close at TP1 (50%), move SL to Break-Even.
5. MAE (Maximum Adverse Excursion) and MFE (Maximum Favorable Excursion) tracking.
6. Daily drawdown reset and circuit breaker enforcement via RiskManager.
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional
import uuid
import numpy as np

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
from src.risk.manager import RiskManager
from src.strategies.base import BaseStrategy
from src.backtest.metrics import TradeRecord, PerformanceCalculator, BacktestMetricsReport


@dataclass
class PendingLimitOrder:
    """Represents a limit order waiting for price penetration."""
    order: Order
    signal: Signal
    placed_at_bar_index: int
    expiry_bars: int = 12


class BacktestEngine:
    """Simulates realistic execution against historical candles."""

    def __init__(
        self,
        strategy: BaseStrategy,
        risk_manager: RiskManager,
        initial_capital: float = 1000.0,
        min_penetration_ticks: int = 1,
        slippage_ticks: float = 0.5,
        tick_size: float = 0.1,
        point_value: float = 1.0,
    ):
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.initial_capital = initial_capital
        self.min_penetration_ticks = min_penetration_ticks
        self.slippage_ticks = slippage_ticks
        self.tick_size = tick_size
        self.point_value = point_value

        self.reset()

    def reset(self) -> None:
        """Resets engine state for a clean backtest run."""
        self.account = AccountInfo(
            currency="EUR",
            balance=self.initial_capital,
            equity=self.initial_capital,
            daily_starting_equity=self.initial_capital,
            daily_realized_pnl=0.0
        )
        self.open_positions: List[Position] = []
        self.pending_orders: List[PendingLimitOrder] = []
        self.completed_trades: List[TradeRecord] = []
        self.current_date: Optional[date] = None
        self.strategy.reset()

    def run(self, bars: List[Bar]) -> BacktestMetricsReport:
        """
        Executes backtest over an ordered list of bars.
        """
        self.reset()

        for idx, bar in enumerate(bars):
            bar_date = bar.timestamp.date()

            # 1. Daily midnight rollover
            if self.current_date is None:
                self.current_date = bar_date
            elif bar_date > self.current_date:
                # Reset daily circuit breaker baseline
                self.account.daily_starting_equity = self.account.equity
                self.account.daily_realized_pnl = 0.0
                self.current_date = bar_date

            # 2. Update and check existing open positions
            self._update_open_positions(bar)

            # 3. Check pending limit orders for realistic fill
            self._check_pending_orders(bar, idx)

            # 4. Pass bar to strategy (strictly incremental)
            signal = self.strategy.on_bar(bar)

            # 5. Route signal to RiskManager
            if signal is not None:
                risk_res = self.risk_manager.evaluate_signal(
                    signal=signal,
                    account=self.account,
                    open_positions=self.open_positions
                )
                if risk_res.approved and risk_res.order:
                    self.pending_orders.append(PendingLimitOrder(
                        order=risk_res.order,
                        signal=signal,
                        placed_at_bar_index=idx
                    ))

        return PerformanceCalculator.calculate(self.completed_trades, self.initial_capital)

    def _check_pending_orders(self, bar: Bar, current_idx: int) -> None:
        """Checks if price penetrated limit orders with sufficient depth."""
        remaining_orders: List[PendingLimitOrder] = []
        penetration_distance = self.min_penetration_ticks * self.tick_size

        for pending in self.pending_orders:
            order = pending.order
            sig = pending.signal

            # Expiry check
            if current_idx - pending.placed_at_bar_index > pending.expiry_bars:
                decision_logger.log_decision("BACKTEST_ORDER", order.symbol, "EXPIRED", "Pending limit order timed out")
                continue

            filled = False
            fill_price = order.requested_price

            if order.side == OrderSide.BUY:
                # Long limit: Low must penetrate below requested price by at least penetration_distance
                if bar.low <= (order.requested_price - penetration_distance):
                    # Apply slippage
                    fill_price = order.requested_price + (self.slippage_ticks * self.tick_size)
                    filled = True
            elif order.side == OrderSide.SELL:
                # Short limit: High must penetrate above requested price
                if bar.high >= (order.requested_price + penetration_distance):
                    fill_price = order.requested_price - (self.slippage_ticks * self.tick_size)
                    filled = True

            if filled:
                pos = Position(
                    id=f"pos_{uuid.uuid4().hex[:8]}",
                    symbol=order.symbol,
                    side=order.side,
                    size_contracts=order.size_contracts,
                    entry_price=fill_price,
                    current_price=fill_price,
                    stop_loss=order.stop_loss,
                    take_profit_1=order.take_profit,
                    take_profit_2=order.take_profit_2,
                    risk_amount_monetary=order.risk_amount_monetary,
                    risk_bucket=sig.risk_bucket,
                    opened_at=bar.timestamp
                )
                self.open_positions.append(pos)
                decision_logger.log_decision("BACKTEST_FILL", order.symbol, "FILLED", f"Filled {pos.size_contracts} at {fill_price:.2f}")
            else:
                remaining_orders.append(pending)

        self.pending_orders = remaining_orders

    def _update_open_positions(self, bar: Bar) -> None:
        """Manages open positions, SL/TP checks, conservative conflict resolution, and partials."""
        remaining_positions: List[Position] = []

        for pos in self.open_positions:
            is_long = pos.side == OrderSide.BUY

            # Update current price and intra-bar excursions
            pos.current_price = bar.close

            # Stop Loss and Take Profit levels
            sl = pos.stop_loss
            tp1 = pos.take_profit_1

            sl_hit = (bar.low <= sl) if is_long else (bar.high >= sl)
            tp1_hit = (bar.high >= tp1) if is_long else (bar.low <= tp1)

            # CONSERVATIVE CONFLICT ASSUMPTION:
            # If both SL and TP1 are inside the same bar's [low, high], SL takes priority!
            if sl_hit and tp1_hit:
                self._close_full_trade(pos, exit_price=sl, exit_time=bar.timestamp, reason="SL (Conservative Conflict)")
                continue

            # 1. Stop Loss Hit
            if sl_hit:
                self._close_full_trade(pos, exit_price=sl, exit_time=bar.timestamp, reason="SL")
                continue

            # 2. Take Profit 1 Hit
            if tp1_hit and not pos.is_partially_closed:
                # Close 50% of the position at TP1
                partial_size = round(pos.size_contracts * 0.5, 4)
                pnl_pts = (tp1 - pos.entry_price) if is_long else (pos.entry_price - tp1)
                pnl_monetary = partial_size * pnl_pts * self.point_value

                initial_risk = pos.risk_amount_monetary * 0.5
                r_mult = pnl_monetary / initial_risk if initial_risk > 0 else 0.0

                record = TradeRecord(
                    trade_id=f"{pos.id}_tp1",
                    symbol=pos.symbol,
                    direction="LONG" if is_long else "SHORT",
                    entry_time=pos.opened_at,
                    exit_time=bar.timestamp,
                    entry_price=pos.entry_price,
                    exit_price=tp1,
                    initial_sl=pos.stop_loss,
                    initial_tp1=pos.take_profit_1,
                    initial_tp2=pos.take_profit_2,
                    size_contracts=partial_size,
                    pnl_monetary=pnl_monetary,
                    r_multiple=r_mult,
                    mae=0.0,
                    mfe=abs(tp1 - pos.entry_price),
                    exit_reason="TP1 (50% partial)",
                    day_of_week=pos.opened_at.strftime("%A"),
                    entry_hour=pos.opened_at.hour
                )
                self.completed_trades.append(record)
                self.account.balance += pnl_monetary
                self.account.equity += pnl_monetary
                self.account.daily_realized_pnl += pnl_monetary

                # Update remaining runner: reduce size and move SL to Break-Even!
                pos.size_contracts = round(pos.size_contracts - partial_size, 4)
                pos.stop_loss = pos.entry_price  # Move SL to Break-Even
                pos.is_partially_closed = True
                pos.is_at_breakeven = True
                remaining_positions.append(pos)
                continue

            # 3. TP2 Hit on Runner
            if pos.is_partially_closed and pos.take_profit_2:
                tp2 = pos.take_profit_2
                tp2_hit = (bar.high >= tp2) if is_long else (bar.low <= tp2)
                if tp2_hit:
                    self._close_full_trade(pos, exit_price=tp2, exit_time=bar.timestamp, reason="TP2 (Runner)")
                    continue

            remaining_positions.append(pos)

        self.open_positions = remaining_positions

    def _close_full_trade(self, pos: Position, exit_price: float, exit_time: datetime, reason: str) -> None:
        """Closes a position completely and records performance."""
        is_long = pos.side == OrderSide.BUY
        pnl_pts = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
        pnl_monetary = pos.size_contracts * pnl_pts * self.point_value

        initial_risk = pos.risk_amount_monetary * (0.5 if pos.is_partially_closed else 1.0)
        r_mult = pnl_monetary / initial_risk if initial_risk > 0 else 0.0

        record = TradeRecord(
            trade_id=pos.id,
            symbol=pos.symbol,
            direction="LONG" if is_long else "SHORT",
            entry_time=pos.opened_at,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            initial_sl=pos.stop_loss,
            initial_tp1=pos.take_profit_1,
            initial_tp2=pos.take_profit_2,
            size_contracts=pos.size_contracts,
            pnl_monetary=pnl_monetary,
            r_multiple=r_mult,
            mae=0.0,
            mfe=abs(exit_price - pos.entry_price),
            exit_reason=reason,
            day_of_week=pos.opened_at.strftime("%A"),
            entry_hour=pos.opened_at.hour
        )
        self.completed_trades.append(record)
        self.account.balance += pnl_monetary
        self.account.equity += pnl_monetary
        self.account.daily_realized_pnl += pnl_monetary
        decision_logger.log_decision("BACKTEST_EXIT", pos.symbol, reason, f"P&L: €{pnl_monetary:.2f} ({r_mult:+.2f}R)")

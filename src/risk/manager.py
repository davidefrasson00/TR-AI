"""
Central Risk Management Engine for TR-AI.
MANDATORY GATEWAY: No trade signal can ever reach the broker without passing this validation.

Enforces:
1. Max 1.0% risk per trade.
2. Max 3.0% daily drawdown circuit breaker.
3. Max 3 concurrent open positions.
4. Correlation buckets (e.g. US500 + USTEC in us_indices: max 1 open position).
5. Dynamic position sizing based on Stop Loss distance and contract specification.
6. Absolute rejection of orders without a valid Stop Loss or below minimum R:R.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import uuid

from src.core.events import (
    AccountInfo,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    Signal,
    SignalDirection,
)
from src.core.logger import decision_logger


@dataclass
class InstrumentSpec:
    """Instrument contract specification for sizing calculations."""
    symbol: str
    point_value: float = 1.0       # Cash value per 1 full point movement
    tick_size: float = 0.1          # Minimum price increment
    min_volume: float = 0.1         # Minimum order size (contracts/lots)
    volume_step: float = 0.1        # Volume increment step
    risk_bucket: str = "default"


@dataclass
class RiskValidationResult:
    """Outcome of risk manager evaluation."""
    approved: bool
    order: Optional[Order] = None
    rejection_reason: Optional[str] = None
    calculated_size: float = 0.0
    risk_amount_monetary: float = 0.0
    risk_percentage: float = 0.0


class RiskManager:
    """Central non-bypassable Risk Gateway."""

    def __init__(
        self,
        max_risk_per_trade_pct: float = 1.0,
        max_daily_drawdown_pct: float = 3.0,
        max_open_positions: int = 3,
        min_risk_reward_ratio: float = 2.0,
        one_position_per_bucket: bool = True,
        kill_switch_active: bool = False,
    ):
        self.max_risk_per_trade_pct = max_risk_per_trade_pct
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.max_open_positions = max_open_positions
        self.min_risk_reward_ratio = min_risk_reward_ratio
        self.one_position_per_bucket = one_position_per_bucket
        self.kill_switch_active = kill_switch_active

        # Default instrument specs
        self.instrument_specs: Dict[str, InstrumentSpec] = {
            "US500": InstrumentSpec(symbol="US500", point_value=1.0, tick_size=0.1, min_volume=0.1, volume_step=0.1, risk_bucket="us_indices"),
            "USTEC": InstrumentSpec(symbol="USTEC", point_value=1.0, tick_size=0.25, min_volume=0.1, volume_step=0.1, risk_bucket="us_indices"),
            "DE40": InstrumentSpec(symbol="DE40", point_value=1.0, tick_size=0.5, min_volume=0.1, volume_step=0.1, risk_bucket="eu_indices"),
        }

    def set_kill_switch(self, active: bool, reason: str = "Manual toggle") -> None:
        """Enables or disables global kill-switch."""
        self.kill_switch_active = active
        decision_logger.log_decision(
            event_type="KILL_SWITCH",
            symbol="ALL",
            action="ACTIVATED" if active else "DEACTIVATED",
            reason=reason
        )

    def evaluate_signal(
        self,
        signal: Signal,
        account: AccountInfo,
        open_positions: List[Position]
    ) -> RiskValidationResult:
        """
        Validates signal and produces sized order or detailed rejection.
        """
        symbol = signal.symbol

        # 1. Kill-Switch check
        if self.kill_switch_active:
            reason = "Global Kill-Switch is active. All new orders blocked."
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason)
            return RiskValidationResult(approved=False, rejection_reason=reason)

        # 2. Daily Drawdown Circuit Breaker check
        if account.daily_drawdown_pct >= self.max_daily_drawdown_pct:
            reason = (
                f"Daily drawdown limit reached ({account.daily_drawdown_pct:.2f}% >= "
                f"{self.max_daily_drawdown_pct:.2f}%). Trading halted for today."
            )
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason, {"daily_dd_pct": account.daily_drawdown_pct})
            return RiskValidationResult(approved=False, rejection_reason=reason)

        # 3. Maximum Open Positions check
        if len(open_positions) >= self.max_open_positions:
            reason = f"Max open positions limit reached ({len(open_positions)}/{self.max_open_positions})"
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason)
            return RiskValidationResult(approved=False, rejection_reason=reason)

        # 4. Correlation Bucket check (e.g. us_indices allows max 1 position)
        spec = self.instrument_specs.get(symbol, InstrumentSpec(symbol=symbol))
        bucket = spec.risk_bucket or signal.risk_bucket

        if self.one_position_per_bucket:
            matching_bucket_positions = [p for p in open_positions if p.risk_bucket == bucket]
            if len(matching_bucket_positions) >= 1:
                conflicting = matching_bucket_positions[0].symbol
                reason = f"Correlation bucket '{bucket}' already has an open position ({conflicting})."
                decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason, {"bucket": bucket})
                return RiskValidationResult(approved=False, rejection_reason=reason)

        # 5. Stop Loss Existence & Distance Sanity check
        stop_distance = signal.stop_distance
        if signal.stop_loss <= 0 or stop_distance <= 0:
            reason = "Mandatory Stop Loss is missing or invalid (stop distance <= 0)."
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason)
            return RiskValidationResult(approved=False, rejection_reason=reason)

        # 6. Minimum Risk/Reward Ratio check
        if signal.risk_reward_ratio < self.min_risk_reward_ratio:
            reason = (
                f"Risk/Reward ratio insufficient ({signal.risk_reward_ratio:.2f} < "
                f"{self.min_risk_reward_ratio:.2f})"
            )
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason, {"rr": signal.risk_reward_ratio})
            return RiskValidationResult(approved=False, rejection_reason=reason)

        # 7. Position Sizing Calculation
        # Monetary risk = Equity * (max_risk_pct / 100)
        max_monetary_risk = account.equity * (self.max_risk_per_trade_pct / 100.0)

        # Ensure cumulative open risk + new risk <= max daily drawdown monetary budget
        daily_loss_budget = account.daily_starting_equity * (self.max_daily_drawdown_pct / 100.0)
        current_open_risk = sum(p.risk_amount_monetary for p in open_positions)
        realized_loss_today = max(0.0, -account.daily_realized_pnl)
        remaining_budget = max(0.0, daily_loss_budget - (current_open_risk + realized_loss_today))

        if remaining_budget <= 0:
            reason = "No remaining daily risk budget for new positions."
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason)
            return RiskValidationResult(approved=False, rejection_reason=reason)

        allowed_monetary_risk = min(max_monetary_risk, remaining_budget)

        # Raw size = Allowed Risk / (Stop Distance * Point Value)
        raw_size = allowed_monetary_risk / (stop_distance * spec.point_value)

        # Round down to allowed volume steps
        steps = int(raw_size / spec.volume_step)
        sized_contracts = round(steps * spec.volume_step, 4)

        if sized_contracts < spec.min_volume:
            reason = (
                f"Calculated size ({sized_contracts:.2f}) is below minimum broker volume "
                f"({spec.min_volume}). Stop is too wide for 1% risk."
            )
            decision_logger.log_decision("RISK_CHECK", symbol, "REJECTED", reason)
            return RiskValidationResult(approved=False, rejection_reason=reason)

        actual_monetary_risk = sized_contracts * stop_distance * spec.point_value
        actual_risk_pct = (actual_monetary_risk / account.equity) * 100.0

        # Construct validated Order
        side = OrderSide.BUY if signal.direction == SignalDirection.LONG else OrderSide.SELL
        order = Order(
            id=f"ord_{uuid.uuid4().hex[:8]}",
            signal_id=signal.id,
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            size_contracts=sized_contracts,
            requested_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,
            take_profit_2=signal.take_profit_2,
            risk_amount_monetary=actual_monetary_risk,
            risk_percentage=actual_risk_pct,
            status=OrderStatus.APPROVED
        )

        decision_logger.log_decision(
            event_type="RISK_CHECK",
            symbol=symbol,
            action="APPROVED",
            reason=f"Order sized to {sized_contracts} contracts with €{actual_monetary_risk:.2f} risk ({actual_risk_pct:.2f}%)",
            details={
                "order_id": order.id,
                "contracts": sized_contracts,
                "risk_eur": round(actual_monetary_risk, 2),
                "risk_pct": round(actual_risk_pct, 2),
                "rr": round(signal.risk_reward_ratio, 2)
            }
        )

        return RiskValidationResult(
            approved=True,
            order=order,
            calculated_size=sized_contracts,
            risk_amount_monetary=actual_monetary_risk,
            risk_percentage=actual_risk_pct
        )

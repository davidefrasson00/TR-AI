"""
Finite State Machine (FSM) for WAM-FVG Strategy.

Tracks and validates sequential phase progression for each instrument and session window:
IDLE -> RANGE_BUILDING -> RANGE_VALID -> SWEEP_DETECTED -> DISPLACEMENT_CONFIRMED -> AWAIT_RETEST -> ORDER_PENDING -> IN_TRADE -> MANAGED -> CLOSED.
Includes terminal/failure paths (NO_RANGE, SWEEP_INVALID, SETUP_EXPIRED, SETUP_INVALIDATED, MISSED).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.logger import decision_logger
from src.strategies.wam_fvg.primitives.range import RangeResult
from src.strategies.wam_fvg.primitives.sweep import SweepResult, SweepDirection
from src.strategies.wam_fvg.primitives.displacement import DisplacementResult
from src.strategies.wam_fvg.primitives.fvg import FairValueGap
from src.strategies.wam_fvg.primitives.fibonacci import FibLevels


class WAMState(str, Enum):
    IDLE = "IDLE"
    RANGE_BUILDING = "RANGE_BUILDING"
    RANGE_VALID = "RANGE_VALID"
    SWEEP_DETECTED = "SWEEP_DETECTED"
    DISPLACEMENT_CONFIRMED = "DISPLACEMENT_CONFIRMED"
    AWAIT_RETEST = "AWAIT_RETEST"
    ORDER_PENDING = "ORDER_PENDING"
    IN_TRADE = "IN_TRADE"
    MANAGED = "MANAGED"
    CLOSED = "CLOSED"

    # Terminal / Invalidation states
    NO_RANGE = "NO_RANGE"
    SWEEP_INVALID = "SWEEP_INVALID"
    SETUP_EXPIRED = "SETUP_EXPIRED"
    SETUP_INVALIDATED = "SETUP_INVALIDATED"
    MISSED = "MISSED"


@dataclass
class FSMContext:
    """Accumulates technical context as the setup develops through the states."""
    symbol: str
    session_name: str
    state: WAMState = WAMState.IDLE
    range_result: Optional[RangeResult] = None
    sweep_result: Optional[SweepResult] = None
    displacement_result: Optional[DisplacementResult] = None
    active_fvg: Optional[FairValueGap] = None
    fib_levels: Optional[FibLevels] = None
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: Optional[float] = None
    confidence_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    rejection_reason: Optional[str] = None
    bars_since_sweep: int = 0
    bars_since_fvg: int = 0
    transition_history: List[Dict[str, Any]] = field(default_factory=list)


class WAMStateMachine:
    """
    Deterministic state machine processor for a single instrument and session.
    """

    def __init__(self, symbol: str, session_name: str):
        self.context = FSMContext(symbol=symbol, session_name=session_name)

    @property
    def current_state(self) -> WAMState:
        return self.context.state

    def transition_to(
        self,
        new_state: WAMState,
        reason: str,
        timestamp: datetime,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Executes and logs a state transition.
        """
        old_state = self.context.state
        self.context.state = new_state
        if new_state in [WAMState.NO_RANGE, WAMState.SWEEP_INVALID, WAMState.SETUP_EXPIRED, WAMState.SETUP_INVALIDATED, WAMState.MISSED]:
            self.context.rejection_reason = reason

        record = {
            "from_state": old_state.value,
            "to_state": new_state.value,
            "timestamp": timestamp.isoformat(),
            "reason": reason,
            "details": details or {}
        }
        self.context.transition_history.append(record)

        decision_logger.log_decision(
            event_type="FSM_TRANSITION",
            symbol=self.context.symbol,
            action=f"{old_state.value} -> {new_state.value}",
            reason=reason,
            details=details
        )

    def reset_for_new_session(self) -> None:
        """Resets state machine back to IDLE at session start."""
        sym = self.context.symbol
        sess = self.context.session_name
        self.context = FSMContext(symbol=sym, session_name=sess, state=WAMState.IDLE)
        decision_logger.info(f"[FSM_RESET] State machine reset to IDLE for {sym} ({sess})")

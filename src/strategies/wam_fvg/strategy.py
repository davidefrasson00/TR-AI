"""
WAM-FVG Strategy Plug-in Implementation.

Coordinates Range Accumulation, Liquidity Sweep, Displacement/MSS, Fair Value Gaps,
Fibonacci OTE confluences, and quantitative scoring to generate high-conviction Signals.
"""

from datetime import datetime
from typing import Dict, List, Optional
import uuid
import pandas as pd

from src.core.events import Bar, Signal, SignalDirection
from src.core.logger import decision_logger
from src.strategies.base import BaseStrategy
from src.strategies.wam_fvg.fsm import WAMStateMachine, WAMState
from src.strategies.wam_fvg.primitives.sessions import (
    SessionManager,
    US_OPEN_TEMPLATE,
    FRANKFURT_OPEN_TEMPLATE,
    SessionTemplate,
)
from src.strategies.wam_fvg.primitives.range import RangeDetector, RangeResult
from src.strategies.wam_fvg.primitives.sweep import SweepDetector, SweepDirection, SweepResult
from src.strategies.wam_fvg.primitives.displacement import DisplacementValidator, DisplacementResult
from src.strategies.wam_fvg.primitives.fvg import FVGDetector, FairValueGap, FVGType, FVGLifecycle
from src.strategies.wam_fvg.primitives.fibonacci import FibonacciCalculator
from src.strategies.wam_fvg.primitives.indicators import calculate_atr
from src.strategies.wam_fvg.scoring import SetupScorer, SetupScore


class WamFvgStrategy(BaseStrategy):
    """
    Wyckoff Accumulation-Manipulation-Distribution + FVG Strategy.
    """

    def __init__(
        self,
        strategy_id: str = "wam_fvg",
        name: str = "Wyckoff AM-Distribution + FVG",
        buffer_ticks: int = 2,
        tp1_offset_ticks: int = 2,
        min_score: float = 60.0,
        min_rr: float = 2.0,
        spread_multiplier: float = 1.5,
    ):
        self.id = strategy_id
        self.name = name
        self.buffer_ticks = buffer_ticks
        self.tp1_offset_ticks = tp1_offset_ticks
        self.min_score = min_score
        self.min_rr = min_rr
        self.spread_multiplier = spread_multiplier

        # Primitives
        self.range_detector = RangeDetector()
        self.sweep_detector = SweepDetector()
        self.displacement_validator = DisplacementValidator(require_mss=True)
        self.fvg_detector = FVGDetector()
        self.fib_calc = FibonacciCalculator()
        self.scorer = SetupScorer(min_score=min_score)

        # State machines and bar storage per symbol
        self.state_machines: Dict[str, WAMStateMachine] = {}
        self.session_managers: Dict[str, SessionManager] = {
            "US500": SessionManager(US_OPEN_TEMPLATE),
            "USTEC": SessionManager(US_OPEN_TEMPLATE),
            "DE40": SessionManager(FRANKFURT_OPEN_TEMPLATE),
        }
        self.bars_history: Dict[str, List[Bar]] = {}
        self.range_bars_history: Dict[str, List[Bar]] = {}

        # Instrument specs (tick size, spread)
        self.tick_sizes: Dict[str, float] = {
            "US500": 0.1,
            "USTEC": 0.25,
            "DE40": 0.5,
        }
        self.typical_spreads: Dict[str, float] = {
            "US500": 0.3,
            "USTEC": 1.0,
            "DE40": 1.2,
        }
        self.last_session_date: Dict[str, date] = {}
        self.current_atr: Dict[str, float] = {}

    def _get_fsm(self, symbol: str) -> WAMStateMachine:
        if symbol not in self.state_machines:
            sess_name = self.session_managers.get(symbol, SessionManager(US_OPEN_TEMPLATE)).template.name
            self.state_machines[symbol] = WAMStateMachine(symbol=symbol, session_name=sess_name)
        return self.state_machines[symbol]

    def reset(self) -> None:
        """Resets all internal history and state machines."""
        for fsm in self.state_machines.values():
            fsm.reset_for_new_session()
        self.bars_history.clear()
        self.range_bars_history.clear()
        self.last_session_date.clear()
        self.current_atr.clear()

    def on_bar(self, bar: Bar, context: Optional[Dict] = None) -> Optional[Signal]:
        """
        Processes a newly closed bar incrementally (no look-ahead).
        """
        symbol = bar.symbol
        fsm = self._get_fsm(symbol)
        sess_mgr = self.session_managers.get(symbol, SessionManager(US_OPEN_TEMPLATE))
        tick_size = self.tick_sizes.get(symbol, 0.1)
        spread = self.typical_spreads.get(symbol, 0.5)

        # Daily Session Rollover: Reset state machine when a new trading day begins
        session_date = sess_mgr.get_session_date(bar.timestamp)
        if symbol not in self.last_session_date:
            self.last_session_date[symbol] = session_date
        elif session_date > self.last_session_date[symbol]:
            fsm.reset_for_new_session()
            self.range_bars_history[symbol] = []
            self.last_session_date[symbol] = session_date

        # Update O(1) Rolling True Range and ATR
        prev_close = self.bars_history[symbol][-1].close if (symbol in self.bars_history and self.bars_history[symbol]) else bar.open
        tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
        alpha = 1.0 / 14.0
        if symbol not in self.current_atr:
            self.current_atr[symbol] = tr
        else:
            self.current_atr[symbol] = (alpha * tr) + ((1.0 - alpha) * self.current_atr[symbol])

        # Scale 5m ATR to M15 equivalent (~sqrt(3) = 1.73)
        atr = self.current_atr[symbol] * (1.732 if bar.timeframe == "5m" else 1.0)
        atr = max(atr, 5.0)

        # Accumulate bar history
        if symbol not in self.bars_history:
            self.bars_history[symbol] = []
        self.bars_history[symbol].append(bar)

        current_state = fsm.current_state

        # -------------------------------------------------------------
        # STATE: IDLE -> RANGE_BUILDING
        # -------------------------------------------------------------
        if current_state == WAMState.IDLE:
            if sess_mgr.is_in_range_window(bar.timestamp):
                fsm.transition_to(
                    WAMState.RANGE_BUILDING,
                    reason="Entered Range Accumulation window",
                    timestamp=bar.timestamp
                )
                if symbol not in self.range_bars_history:
                    self.range_bars_history[symbol] = []
                self.range_bars_history[symbol].append(bar)
            return None

        # -------------------------------------------------------------
        # STATE: RANGE_BUILDING
        # -------------------------------------------------------------
        if current_state == WAMState.RANGE_BUILDING:
            if sess_mgr.is_in_range_window(bar.timestamp):
                self.range_bars_history[symbol].append(bar)
                return None
            else:
                # Range window ended -> Evaluate range validity
                range_bars = self.range_bars_history.get(symbol, [])
                if len(range_bars) >= 6:
                    df_range = pd.DataFrame([{"open": b.open, "high": b.high, "low": b.low, "close": b.close} for b in range_bars])
                    range_res = self.range_detector.evaluate_range(df_range, atr=atr)

                    if range_res.is_valid:
                        fsm.context.range_result = range_res
                        fsm.transition_to(
                            WAMState.RANGE_VALID,
                            reason=f"Valid Range established: [{range_res.low:.2f} - {range_res.high:.2f}] (ER={range_res.efficiency_ratio:.2f})",
                            timestamp=bar.timestamp,
                            details={"high": range_res.high, "low": range_res.low, "height": range_res.height}
                        )
                    else:
                        fsm.transition_to(
                            WAMState.NO_RANGE,
                            reason=f"Range invalid: {range_res.rejection_reason}",
                            timestamp=bar.timestamp
                        )
                        return None
                else:
                    fsm.transition_to(
                        WAMState.NO_RANGE,
                        reason="Insufficient bars during range window",
                        timestamp=bar.timestamp
                    )
                    return None

        # -------------------------------------------------------------
        # STATE: RANGE_VALID -> SWEEP_DETECTED
        # -------------------------------------------------------------
        if fsm.current_state == WAMState.RANGE_VALID:
            if not sess_mgr.is_in_manipulation_window(bar.timestamp):
                fsm.transition_to(
                    WAMState.SETUP_EXPIRED,
                    reason="Exceeded manipulation window without sweep",
                    timestamp=bar.timestamp
                )
                return None

            range_res = fsm.context.range_result
            if range_res is None:
                return None

            sweep_res = self.sweep_detector.evaluate_bar(
                bar_high=bar.high,
                bar_low=bar.low,
                bar_close=bar.close,
                range_high=range_res.high,
                range_low=range_res.low,
                range_height=range_res.height
            )

            if sweep_res.is_valid:
                fsm.context.sweep_result = sweep_res
                fsm.context.bars_since_sweep = 0
                direction_label = "Spring (Long candidate)" if sweep_res.direction == SweepDirection.BULLISH_SPRING else "UTAD (Short candidate)"
                fsm.transition_to(
                    WAMState.SWEEP_DETECTED,
                    reason=f"Valid {direction_label} at {sweep_res.sweep_extreme:.2f} (depth={sweep_res.depth_fraction:.2f}x range)",
                    timestamp=bar.timestamp,
                    details={"extreme": sweep_res.sweep_extreme, "depth_frac": sweep_res.depth_fraction}
                )
            elif "over-extended" in (sweep_res.rejection_reason or "") or "consecutive closes beyond" in (sweep_res.rejection_reason or ""):
                fsm.transition_to(
                    WAMState.SWEEP_INVALID,
                    reason=sweep_res.rejection_reason or "Invalid sweep",
                    timestamp=bar.timestamp
                )
            return None

        # -------------------------------------------------------------
        # STATE: SWEEP_DETECTED -> DISPLACEMENT_CONFIRMED
        # -------------------------------------------------------------
        if fsm.current_state == WAMState.SWEEP_DETECTED:
            fsm.context.bars_since_sweep += 1
            if fsm.context.bars_since_sweep > 12:
                fsm.transition_to(
                    WAMState.SETUP_EXPIRED,
                    reason="Displacement timeout (>12 bars since sweep)",
                    timestamp=bar.timestamp
                )
                return None

            range_res = fsm.context.range_result
            sweep_res = fsm.context.sweep_result
            if range_res is None or sweep_res is None:
                return None

            # Check if this bar qualifies as Displacement + MSS
            # Use range boundary as conservative swing pivot if local pivot not yet isolated
            swing_pivot = range_res.low if sweep_res.direction == SweepDirection.BULLISH_SPRING else range_res.high
            disp_res = self.displacement_validator.evaluate_bar(
                bar_open=bar.open,
                bar_high=bar.high,
                bar_low=bar.low,
                bar_close=bar.close,
                range_high=range_res.high,
                range_low=range_res.low,
                atr=atr,
                sweep_direction=sweep_res.direction,
                local_swing_pivot=swing_pivot
            )

            if disp_res.is_valid:
                fsm.context.displacement_result = disp_res

                # Check if an FVG was formed between bar t-2 and bar t
                history = self.bars_history[symbol]
                if len(history) >= 3:
                    b_prev2 = history[-3]
                    fvg = self.fvg_detector.detect_fvg(
                        bar_prev2_high=b_prev2.high,
                        bar_prev2_low=b_prev2.low,
                        bar_curr_high=bar.high,
                        bar_curr_low=bar.low,
                        bar_index=len(history),
                        atr=atr
                    )
                    if fvg:
                        fsm.context.active_fvg = fvg

                # If no FVG on this exact bar, create an active imbalance zone spanning displacement body
                if not fsm.context.active_fvg:
                    fvg_type = FVGType.BULLISH if sweep_res.direction == SweepDirection.BULLISH_SPRING else FVGType.BEARISH
                    top = bar.close if fvg_type == FVGType.BULLISH else bar.open
                    bottom = bar.open if fvg_type == FVGType.BULLISH else bar.close
                    fsm.context.active_fvg = FairValueGap.create(fvg_type, top=top, bottom=bottom, bar_index=len(history))

                fsm.transition_to(
                    WAMState.DISPLACEMENT_CONFIRMED,
                    reason=f"Displacement & MSS confirmed (body={disp_res.body_atr_ratio:.2f}x ATR, extreme={disp_res.displacement_extreme:.2f})",
                    timestamp=bar.timestamp
                )

                # Move directly to AWAIT_RETEST
                fsm.transition_to(
                    WAMState.AWAIT_RETEST,
                    reason="Calculating OTE and confluence entry zone",
                    timestamp=bar.timestamp
                )
            return None

        # -------------------------------------------------------------
        # STATE: AWAIT_RETEST -> ORDER_PENDING (Signal Generation)
        # -------------------------------------------------------------
        if fsm.current_state == WAMState.AWAIT_RETEST:
            range_res = fsm.context.range_result
            sweep_res = fsm.context.sweep_result
            disp_res = fsm.context.displacement_result
            fvg = fsm.context.active_fvg

            if not range_res or not sweep_res or not disp_res or not fvg:
                return None

            # Calculate Fib levels & OTE zone
            fibs = self.fib_calc.calculate_levels(
                sweep_extreme=sweep_res.sweep_extreme,
                displacement_extreme=disp_res.displacement_extreme,
                direction=sweep_res.direction
            )
            fsm.context.fib_levels = fibs

            confluence = FibonacciCalculator.get_fvg_ote_confluence(
                fvg_top=fvg.top,
                fvg_bottom=fvg.bottom,
                ote_top=fibs.ote_top,
                ote_bottom=fibs.ote_bottom
            )
            has_ote_confluence = confluence is not None

            # Determine Entry price
            if confluence:
                entry_price = (confluence[0] + confluence[1]) / 2.0
            else:
                entry_price = fvg.consequent_encroachment

            # Determine Stop Loss (sweep_extreme + buffer)
            # Short position must account for Ask spread!
            buffer_dist = max(self.buffer_ticks * tick_size, spread * self.spread_multiplier)
            if sweep_res.direction == SweepDirection.BULLISH_SPRING:
                stop_loss = sweep_res.sweep_extreme - buffer_dist
                direction = SignalDirection.LONG
                # TP1: opposite range high + offset ticks
                take_profit_1 = range_res.high + (self.tp1_offset_ticks * tick_size)
                take_profit_2 = fibs.level_0 + (0.272 * abs(disp_res.displacement_extreme - sweep_res.sweep_extreme))
            else:
                stop_loss = sweep_res.sweep_extreme + buffer_dist + spread
                direction = SignalDirection.SHORT
                # TP1: opposite range low - offset ticks
                take_profit_1 = range_res.low - (self.tp1_offset_ticks * tick_size)
                take_profit_2 = fibs.level_0 - (0.272 * abs(disp_res.displacement_extreme - sweep_res.sweep_extreme))

            # Score Setup
            score_report = self.scorer.score_setup(
                range_res=range_res,
                sweep_res=sweep_res,
                disp_res=disp_res,
                fvg=fvg,
                has_ote_confluence=has_ote_confluence
            )

            fsm.context.confidence_score = score_report.total_score
            fsm.context.score_breakdown = score_report.breakdown

            if not score_report.is_qualified:
                fsm.transition_to(
                    WAMState.SETUP_INVALIDATED,
                    reason=f"Setup score insufficient: {score_report.rationale}",
                    timestamp=bar.timestamp
                )
                return None

            # Generate Signal
            fsm.context.entry_price = entry_price
            fsm.context.stop_loss = stop_loss
            fsm.context.take_profit_1 = take_profit_1
            fsm.context.take_profit_2 = take_profit_2

            fsm.transition_to(
                WAMState.ORDER_PENDING,
                reason=f"Setup armed at {entry_price:.2f} (SL={stop_loss:.2f}, TP1={take_profit_1:.2f}) with score {score_report.total_score:.1f}",
                timestamp=bar.timestamp
            )

            signal = Signal(
                id=f"sig_{uuid.uuid4().hex[:8]}",
                strategy_id=self.id,
                symbol=symbol,
                direction=direction,
                timeframe=bar.timeframe,
                entry_price=round(entry_price, 2),
                stop_loss=round(stop_loss, 2),
                take_profit_1=round(take_profit_1, 2),
                take_profit_2=round(take_profit_2, 2) if take_profit_2 else None,
                confidence_score=score_report.total_score,
                risk_bucket="us_indices" if symbol in ["US500", "USTEC"] else "eu_indices",
                rationale=score_report.rationale,
                score_breakdown=score_report.breakdown
            )

            decision_logger.log_decision(
                event_type="SIGNAL_GENERATED",
                symbol=symbol,
                action=direction.value,
                reason=signal.rationale,
                details={
                    "entry": signal.entry_price,
                    "sl": signal.stop_loss,
                    "tp1": signal.take_profit_1,
                    "rr": round(signal.risk_reward_ratio, 2),
                    "score": signal.confidence_score
                }
            )

            return signal

        return None

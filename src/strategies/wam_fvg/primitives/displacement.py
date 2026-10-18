"""
Displacement and Market Structure Shift (MSS) Primitive.

Validates the impulsive re-entry of price into the range following a sweep:
1. Significant body size relative to ATR.
2. Directional close in the extreme percentage of the bar.
3. Chiusura back inside the accumulation range.
4. Market Structure Shift (break of the local opposing swing pivot).
"""

from dataclasses import dataclass
from typing import Optional
from src.strategies.wam_fvg.primitives.sweep import SweepDirection


@dataclass
class DisplacementResult:
    """Outcome of a displacement and MSS evaluation."""
    is_valid: bool
    body_atr_ratio: float = 0.0
    close_extreme_pct: float = 0.0
    is_inside_range: bool = False
    has_mss: bool = False
    displacement_extreme: float = 0.0
    rejection_reason: Optional[str] = None


class DisplacementValidator:
    """
    Evaluates candidate re-entry bars following a confirmed sweep.
    """

    def __init__(
        self,
        min_body_atr: float = 1.0,
        close_in_extreme_pct: float = 30.0,
        require_mss: bool = True,
    ):
        self.min_body_atr = min_body_atr
        self.close_in_extreme_pct = close_in_extreme_pct
        self.require_mss = require_mss

    def evaluate_bar(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        range_high: float,
        range_low: float,
        atr: float,
        sweep_direction: SweepDirection,
        local_swing_pivot: Optional[float] = None
    ) -> DisplacementResult:
        """
        Validates if the closed bar qualifies as a strong displacement leg.
        """
        bar_range = bar_high - bar_low
        if bar_range <= 0 or atr <= 0:
            return DisplacementResult(is_valid=False, rejection_reason="Invalid bar range or zero ATR")

        body = abs(bar_close - bar_open)
        body_atr_ratio = body / atr

        # 1. Body vs ATR check
        if body_atr_ratio < self.min_body_atr:
            return DisplacementResult(
                is_valid=False,
                body_atr_ratio=body_atr_ratio,
                rejection_reason=f"Weak body relative to ATR ({body_atr_ratio:.2f} < {self.min_body_atr})"
            )

        # 2. Bullish Displacement (Following Spring below Range Low)
        if sweep_direction == SweepDirection.BULLISH_SPRING:
            if bar_close <= bar_open:
                return DisplacementResult(
                    is_valid=False,
                    rejection_reason="Candle direction does not match Bullish Spring"
                )

            # Close must be in the top X% of the candle range
            close_from_high_pct = ((bar_high - bar_close) / bar_range) * 100.0
            if close_from_high_pct > self.close_in_extreme_pct:
                return DisplacementResult(
                    is_valid=False,
                    body_atr_ratio=body_atr_ratio,
                    close_extreme_pct=close_from_high_pct,
                    rejection_reason=f"Close not sufficiently near high ({close_from_high_pct:.1f}% > {self.close_in_extreme_pct}%)"
                )

            # Re-entry inside range: Close must be >= Range Low
            is_inside = bar_close >= range_low
            if not is_inside:
                return DisplacementResult(
                    is_valid=False,
                    body_atr_ratio=body_atr_ratio,
                    close_extreme_pct=close_from_high_pct,
                    is_inside_range=False,
                    rejection_reason="Bar failed to close back inside range boundary"
                )

            # MSS check: Close must exceed the local swing high formed during sweep
            has_mss = True
            if self.require_mss and local_swing_pivot is not None:
                has_mss = bar_close > local_swing_pivot
                if not has_mss:
                    return DisplacementResult(
                        is_valid=False,
                        body_atr_ratio=body_atr_ratio,
                        close_extreme_pct=close_from_high_pct,
                        is_inside_range=True,
                        has_mss=False,
                        rejection_reason=f"Failed MSS: close ({bar_close}) did not break swing high ({local_swing_pivot})"
                    )

            return DisplacementResult(
                is_valid=True,
                body_atr_ratio=body_atr_ratio,
                close_extreme_pct=close_from_high_pct,
                is_inside_range=True,
                has_mss=has_mss,
                displacement_extreme=bar_high
            )

        # 3. Bearish Displacement (Following UTAD above Range High)
        elif sweep_direction == SweepDirection.BEARISH_UTAD:
            if bar_close >= bar_open:
                return DisplacementResult(
                    is_valid=False,
                    rejection_reason="Candle direction does not match Bearish UTAD"
                )

            # Close must be in the bottom X% of the candle range
            close_from_low_pct = ((bar_close - bar_low) / bar_range) * 100.0
            if close_from_low_pct > self.close_in_extreme_pct:
                return DisplacementResult(
                    is_valid=False,
                    body_atr_ratio=body_atr_ratio,
                    close_extreme_pct=close_from_low_pct,
                    rejection_reason=f"Close not sufficiently near low ({close_from_low_pct:.1f}% > {self.close_in_extreme_pct}%)"
                )

            # Re-entry inside range: Close must be <= Range High
            is_inside = bar_close <= range_high
            if not is_inside:
                return DisplacementResult(
                    is_valid=False,
                    body_atr_ratio=body_atr_ratio,
                    close_extreme_pct=close_from_low_pct,
                    is_inside_range=False,
                    rejection_reason="Bar failed to close back inside range boundary"
                )

            # MSS check: Close must break below local swing low formed during sweep
            has_mss = True
            if self.require_mss and local_swing_pivot is not None:
                has_mss = bar_close < local_swing_pivot
                if not has_mss:
                    return DisplacementResult(
                        is_valid=False,
                        body_atr_ratio=body_atr_ratio,
                        close_extreme_pct=close_from_low_pct,
                        is_inside_range=True,
                        has_mss=False,
                        rejection_reason=f"Failed MSS: close ({bar_close}) did not break swing low ({local_swing_pivot})"
                    )

            return DisplacementResult(
                is_valid=True,
                body_atr_ratio=body_atr_ratio,
                close_extreme_pct=close_from_low_pct,
                is_inside_range=True,
                has_mss=has_mss,
                displacement_extreme=bar_low
            )

        return DisplacementResult(is_valid=False, rejection_reason="Unknown sweep direction")

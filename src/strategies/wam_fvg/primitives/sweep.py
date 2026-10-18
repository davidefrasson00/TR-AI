"""
Liquidity Sweep (Manipulation / Spring / UTAD) Detection Primitive.

Identifies liquidity sweeps beyond the accumulation range, validates penetration depth
relative to range height, and filters out genuine trend breakouts via consecutive close count.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SweepDirection(str, Enum):
    BULLISH_SPRING = "BULLISH_SPRING"  # Sweep below Range Low (Long candidate)
    BEARISH_UTAD = "BEARISH_UTAD"      # Sweep above Range High (Short candidate)


@dataclass
class SweepResult:
    """Outcome of a liquidity sweep evaluation."""
    is_valid: bool
    direction: Optional[SweepDirection] = None
    sweep_level: float = 0.0
    sweep_extreme: float = 0.0
    depth_absolute: float = 0.0
    depth_fraction: float = 0.0
    closes_beyond_count: int = 0
    rejection_reason: Optional[str] = None


class SweepDetector:
    """
    Monitors bars during the manipulation window to detect Wyckoff Phase C sweeps.
    """

    def __init__(
        self,
        min_depth_frac: float = 0.03,
        max_depth_frac: float = 0.50,
        max_closes_beyond: int = 2,
    ):
        self.min_depth_frac = min_depth_frac
        self.max_depth_frac = max_depth_frac
        self.max_closes_beyond = max_closes_beyond

    def evaluate_bar(
        self,
        bar_high: float,
        bar_low: float,
        bar_close: float,
        range_high: float,
        range_low: float,
        range_height: float,
        prior_closes_beyond: int = 0
    ) -> SweepResult:
        """
        Evaluates a closed bar against the range boundary.
        """
        if range_height <= 0:
            return SweepResult(is_valid=False, rejection_reason="Invalid range height")

        # 1. Check for Bullish Spring (Sweep below Range Low)
        if bar_low < range_low:
            depth = range_low - bar_low
            depth_frac = depth / range_height
            closes_beyond = prior_closes_beyond + (1 if bar_close < range_low else 0)

            # Rejection check 1: Depth too shallow (noise)
            if depth_frac < self.min_depth_frac:
                return SweepResult(
                    is_valid=False,
                    direction=SweepDirection.BULLISH_SPRING,
                    sweep_level=range_low,
                    sweep_extreme=bar_low,
                    depth_absolute=depth,
                    depth_fraction=depth_frac,
                    closes_beyond_count=closes_beyond,
                    rejection_reason=f"Sweep depth too shallow ({depth_frac:.3f} < {self.min_depth_frac})"
                )

            # Rejection check 2: Depth too large (genuine breakout)
            if depth_frac > self.max_depth_frac:
                return SweepResult(
                    is_valid=False,
                    direction=SweepDirection.BULLISH_SPRING,
                    sweep_level=range_low,
                    sweep_extreme=bar_low,
                    depth_absolute=depth,
                    depth_fraction=depth_frac,
                    closes_beyond_count=closes_beyond,
                    rejection_reason=f"Sweep depth over-extended ({depth_frac:.3f} > {self.max_depth_frac})"
                )

            # Rejection check 3: Too many closes beyond range (acceptance / real breakout)
            if closes_beyond > self.max_closes_beyond:
                return SweepResult(
                    is_valid=False,
                    direction=SweepDirection.BULLISH_SPRING,
                    sweep_level=range_low,
                    sweep_extreme=bar_low,
                    depth_absolute=depth,
                    depth_fraction=depth_frac,
                    closes_beyond_count=closes_beyond,
                    rejection_reason=f"Too many consecutive closes beyond level ({closes_beyond} > {self.max_closes_beyond})"
                )

            return SweepResult(
                is_valid=True,
                direction=SweepDirection.BULLISH_SPRING,
                sweep_level=range_low,
                sweep_extreme=bar_low,
                depth_absolute=depth,
                depth_fraction=depth_frac,
                closes_beyond_count=closes_beyond
            )

        # 2. Check for Bearish UTAD (Sweep above Range High)
        if bar_high > range_high:
            depth = bar_high - range_high
            depth_frac = depth / range_height
            closes_beyond = prior_closes_beyond + (1 if bar_close > range_high else 0)

            # Rejection check 1: Depth too shallow
            if depth_frac < self.min_depth_frac:
                return SweepResult(
                    is_valid=False,
                    direction=SweepDirection.BEARISH_UTAD,
                    sweep_level=range_high,
                    sweep_extreme=bar_high,
                    depth_absolute=depth,
                    depth_fraction=depth_frac,
                    closes_beyond_count=closes_beyond,
                    rejection_reason=f"Sweep depth too shallow ({depth_frac:.3f} < {self.min_depth_frac})"
                )

            # Rejection check 2: Depth over-extended
            if depth_frac > self.max_depth_frac:
                return SweepResult(
                    is_valid=False,
                    direction=SweepDirection.BEARISH_UTAD,
                    sweep_level=range_high,
                    sweep_extreme=bar_high,
                    depth_absolute=depth,
                    depth_fraction=depth_frac,
                    closes_beyond_count=closes_beyond,
                    rejection_reason=f"Sweep depth over-extended ({depth_frac:.3f} > {self.max_depth_frac})"
                )

            # Rejection check 3: Too many closes beyond level
            if closes_beyond > self.max_closes_beyond:
                return SweepResult(
                    is_valid=False,
                    direction=SweepDirection.BEARISH_UTAD,
                    sweep_level=range_high,
                    sweep_extreme=bar_high,
                    depth_absolute=depth,
                    depth_fraction=depth_frac,
                    closes_beyond_count=closes_beyond,
                    rejection_reason=f"Too many consecutive closes beyond level ({closes_beyond} > {self.max_closes_beyond})"
                )

            return SweepResult(
                is_valid=True,
                direction=SweepDirection.BEARISH_UTAD,
                sweep_level=range_high,
                sweep_extreme=bar_high,
                depth_absolute=depth,
                depth_fraction=depth_frac,
                closes_beyond_count=closes_beyond
            )

        return SweepResult(is_valid=False, rejection_reason="Price did not exceed range boundaries")

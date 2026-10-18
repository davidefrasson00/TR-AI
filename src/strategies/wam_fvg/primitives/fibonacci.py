"""
Fibonacci Retracement and Optimal Trade Entry (OTE) Primitive.

Calculates Fibonacci levels on the impulse swing (from sweep extreme to displacement extreme),
identifies the OTE zone (0.62 - 0.79), and determines geometric confluence with Fair Value Gaps.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from src.strategies.wam_fvg.primitives.sweep import SweepDirection


@dataclass
class FibLevels:
    """Fibonacci retracement price levels for an impulse leg."""
    level_0: float     # 0.0: Displacement extreme
    level_50: float    # 0.50: Equilibrium
    level_618: float   # 0.618: Golden ratio
    level_705: float   # 0.705: ICT Sweet Spot
    level_786: float   # 0.786: Deep retracement
    level_100: float   # 1.00: Sweep extreme (invalidation)
    ote_top: float
    ote_bottom: float


class FibonacciCalculator:
    """Calculates retracement geometry for entry optimization."""

    def __init__(
        self,
        ote_low: float = 0.62,
        ote_high: float = 0.79,
    ):
        self.ote_low = ote_low
        self.ote_high = ote_high

    def calculate_levels(
        self,
        sweep_extreme: float,
        displacement_extreme: float,
        direction: SweepDirection
    ) -> FibLevels:
        """
        Calculates Fib levels where 0% is displacement extreme and 100% is sweep extreme.
        - For Bullish Spring: sweep_extreme is low (100%), displacement_extreme is high (0%).
          Pullback moves downward from high toward low.
        - For Bearish UTAD: sweep_extreme is high (100%), displacement_extreme is low (0%).
          Pullback moves upward from low toward high.
        """
        leg = abs(displacement_extreme - sweep_extreme)

        if direction == SweepDirection.BULLISH_SPRING:
            # Bullish leg: High = displacement_extreme, Low = sweep_extreme
            high = displacement_extreme
            low = sweep_extreme

            lvl_0 = high
            lvl_50 = high - (0.50 * leg)
            lvl_618 = high - (0.618 * leg)
            lvl_705 = high - (0.705 * leg)
            lvl_786 = high - (0.786 * leg)
            lvl_100 = low

            ote_top = high - (self.ote_low * leg)     # Less deep (higher price)
            ote_bottom = high - (self.ote_high * leg) # Deeper (lower price)

        else:
            # Bearish leg: Low = displacement_extreme, High = sweep_extreme
            low = displacement_extreme
            high = sweep_extreme

            lvl_0 = low
            lvl_50 = low + (0.50 * leg)
            lvl_618 = low + (0.618 * leg)
            lvl_705 = low + (0.705 * leg)
            lvl_786 = low + (0.786 * leg)
            lvl_100 = high

            ote_bottom = low + (self.ote_low * leg)   # Less deep (lower price)
            ote_top = low + (self.ote_high * leg)      # Deeper (higher price)

        return FibLevels(
            level_0=lvl_0,
            level_50=lvl_50,
            level_618=lvl_618,
            level_705=lvl_705,
            level_786=lvl_786,
            level_100=lvl_100,
            ote_top=ote_top,
            ote_bottom=ote_bottom
        )

    @staticmethod
    def get_fvg_ote_confluence(
        fvg_top: float,
        fvg_bottom: float,
        ote_top: float,
        ote_bottom: float
    ) -> Optional[Tuple[float, float]]:
        """
        Calculates the mathematical intersection between an FVG and the OTE zone.
        Returns (confluence_bottom, confluence_top) or None if disjoint.
        """
        c_bottom = max(min(fvg_bottom, fvg_top), min(ote_bottom, ote_top))
        c_top = min(max(fvg_bottom, fvg_top), max(ote_bottom, ote_top))

        if c_bottom < c_top:
            return c_bottom, c_top
        return None

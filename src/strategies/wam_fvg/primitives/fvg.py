"""
Fair Value Gap (FVG) Primitive.

Strict 3-candle price imbalance detection without look-ahead bias.
Calculates Consequent Encroachment (CE 50%), size filters against ATR,
and manages lifecycle state progression (INTACT -> TOUCHED -> CE_HIT -> FILLED -> INVERTED).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FVGType(str, Enum):
    BULLISH = "BULLISH"  # Imbalance to the upside (support zone)
    BEARISH = "BEARISH"  # Imbalance to the downside (resistance zone)


class FVGLifecycle(str, Enum):
    INTACT = "INTACT"
    TOUCHED = "TOUCHED"
    CE_HIT = "CE_HIT"        # Retested to at least 50% depth
    FILLED = "FILLED"        # Completely mitigated
    INVERTED = "INVERTED"    # Failed & flipped direction (invalidates setup)


@dataclass
class FairValueGap:
    """Represents a validated 3-candle Fair Value Gap."""
    fvg_type: FVGType
    top: float
    bottom: float
    bar_index: int
    size: float
    consequent_encroachment: float
    lifecycle: FVGLifecycle = FVGLifecycle.INTACT
    fill_percentage: float = 0.0

    @classmethod
    def create(
        cls,
        fvg_type: FVGType,
        top: float,
        bottom: float,
        bar_index: int
    ) -> "FairValueGap":
        size = top - bottom
        ce = (top + bottom) / 2.0
        return cls(
            fvg_type=fvg_type,
            top=top,
            bottom=bottom,
            bar_index=bar_index,
            size=size,
            consequent_encroachment=ce,
            lifecycle=FVGLifecycle.INTACT,
            fill_percentage=0.0
        )

    def update_with_candle(self, bar_high: float, bar_low: float, bar_close: float) -> None:
        """
        Updates the lifecycle status of the FVG as subsequent candles unfold.
        """
        if self.lifecycle == FVGLifecycle.INVERTED:
            return

        if self.fvg_type == FVGType.BULLISH:
            # Bullish FVG zone: [bottom, top] (acts as support on pullback)
            if bar_low < self.top:
                if self.lifecycle == FVGLifecycle.INTACT:
                    self.lifecycle = FVGLifecycle.TOUCHED

                # Measure how deeply price penetrated into the gap
                penetration = self.top - min(bar_low, self.top)
                fill_pct = min(100.0, (penetration / self.size) * 100.0) if self.size > 0 else 100.0
                self.fill_percentage = max(self.fill_percentage, fill_pct)

                if bar_low <= self.consequent_encroachment:
                    self.lifecycle = FVGLifecycle.CE_HIT

                if bar_low <= self.bottom:
                    self.lifecycle = FVGLifecycle.FILLED

                # Inversion: Bar closed below the bottom of the bullish gap
                if bar_close < self.bottom:
                    self.lifecycle = FVGLifecycle.INVERTED

        elif self.fvg_type == FVGType.BEARISH:
            # Bearish FVG zone: [bottom, top] (acts as resistance on pullback)
            if bar_high > self.bottom:
                if self.lifecycle == FVGLifecycle.INTACT:
                    self.lifecycle = FVGLifecycle.TOUCHED

                penetration = max(bar_high, self.bottom) - self.bottom
                fill_pct = min(100.0, (penetration / self.size) * 100.0) if self.size > 0 else 100.0
                self.fill_percentage = max(self.fill_percentage, fill_pct)

                if bar_high >= self.consequent_encroachment:
                    self.lifecycle = FVGLifecycle.CE_HIT

                if bar_high >= self.top:
                    self.lifecycle = FVGLifecycle.FILLED

                # Inversion: Bar closed above the top of the bearish gap
                if bar_close > self.top:
                    self.lifecycle = FVGLifecycle.INVERTED


class FVGDetector:
    """
    Evaluates 3 consecutive closed bars to identify new Fair Value Gaps.
    """

    def __init__(
        self,
        min_size_atr: float = 0.15,
        max_size_atr: float = 2.0,
    ):
        self.min_size_atr = min_size_atr
        self.max_size_atr = max_size_atr

    def detect_fvg(
        self,
        bar_prev2_high: float,
        bar_prev2_low: float,
        bar_curr_high: float,
        bar_curr_low: float,
        bar_index: int,
        atr: float
    ) -> Optional[FairValueGap]:
        """
        Determines if there is an FVG between bar t-2 and bar t.
        No look-ahead: bar_curr is the just-closed bar at index bar_index.
        """
        if atr <= 0:
            return None

        # 1. Bullish FVG: Low of bar t is strictly above High of bar t-2
        if bar_curr_low > bar_prev2_high:
            top = bar_curr_low
            bottom = bar_prev2_high
            gap_size = top - bottom
            size_atr = gap_size / atr

            if self.min_size_atr <= size_atr <= self.max_size_atr:
                return FairValueGap.create(
                    fvg_type=FVGType.BULLISH,
                    top=top,
                    bottom=bottom,
                    bar_index=bar_index
                )

        # 2. Bearish FVG: High of bar t is strictly below Low of bar t-2
        elif bar_curr_high < bar_prev2_low:
            top = bar_prev2_low
            bottom = bar_curr_high
            gap_size = top - bottom
            size_atr = gap_size / atr

            if self.min_size_atr <= size_atr <= self.max_size_atr:
                return FairValueGap.create(
                    fvg_type=FVGType.BEARISH,
                    top=top,
                    bottom=bottom,
                    bar_index=bar_index
                )

        return None

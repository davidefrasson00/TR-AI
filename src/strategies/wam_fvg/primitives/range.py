"""
Range Accumulation Detection and Validation Primitive.

Calculates session high/low, equilibrium (midpoint), premium/discount zones,
and enforces non-trending lateral consolidation criteria using Kaufman Efficiency Ratio (ER)
and ATR bounds.
"""

from dataclasses import dataclass
from typing import Optional, List
import pandas as pd
import numpy as np


@dataclass
class RangeResult:
    """Outcome of a range validation process."""
    high: float
    low: float
    height: float
    midpoint: float
    is_valid: bool
    rejection_reason: Optional[str] = None
    efficiency_ratio: float = 0.0
    height_atr_ratio: float = 0.0
    bars_inside_pct: float = 0.0
    bar_count: int = 0

    @property
    def premium_zone(self) -> tuple[float, float]:
        """Upper half of the range [midpoint, high]."""
        return self.midpoint, self.high

    @property
    def discount_zone(self) -> tuple[float, float]:
        """Lower half of the range [low, midpoint]."""
        return self.low, self.midpoint


def calculate_kaufman_efficiency_ratio(closes: pd.Series) -> float:
    """
    Kaufman Efficiency Ratio (ER):
    Direction / Volatility = |Close_N - Close_0| / Sum(|Close_t - Close_{t-1}|)
    Values close to 1.0 indicate a strong clean trend.
    Values close to 0.0 indicate choppy/lateral consolidation.
    """
    if len(closes) < 2:
        return 0.0
    net_change = abs(closes.iloc[-1] - closes.iloc[0])
    total_change = (closes.diff().abs()).sum()
    if total_change == 0 or np.isnan(total_change):
        return 0.0
    return float(net_change / total_change)


class RangeDetector:
    """Validates if price action during the accumulation window constitutes a valid Wyckoff range."""

    def __init__(
        self,
        min_height_atr: float = 0.5,
        max_height_atr: float = 2.5,
        min_bars_inside_pct: float = 70.0,
        max_efficiency_ratio: float = 0.35,
        min_bars_count: int = 6,
    ):
        self.min_height_atr = min_height_atr
        self.max_height_atr = max_height_atr
        self.min_bars_inside_pct = min_bars_inside_pct
        self.max_efficiency_ratio = max_efficiency_ratio
        self.min_bars_count = min_bars_count

    def evaluate_range(
        self,
        bars_df: pd.DataFrame,
        atr: float
    ) -> RangeResult:
        """
        Evaluates a slice of OHLCV bars belonging to the range accumulation window.
        Expected columns in bars_df: ['open', 'high', 'low', 'close']
        """
        if len(bars_df) < self.min_bars_count:
            return RangeResult(
                high=0.0, low=0.0, height=0.0, midpoint=0.0,
                is_valid=False,
                rejection_reason=f"Insufficient bars in range window ({len(bars_df)} < {self.min_bars_count})",
                bar_count=len(bars_df)
            )

        high = float(bars_df['high'].max())
        low = float(bars_df['low'].min())
        height = high - low
        midpoint = (high + low) / 2.0

        if height <= 0 or atr <= 0:
            return RangeResult(
                high=high, low=low, height=height, midpoint=midpoint,
                is_valid=False,
                rejection_reason="Invalid zero or negative range height or ATR",
                bar_count=len(bars_df)
            )

        # 1. Height vs ATR check
        height_atr_ratio = height / atr
        if height_atr_ratio < self.min_height_atr:
            return RangeResult(
                high=high, low=low, height=height, midpoint=midpoint,
                is_valid=False,
                rejection_reason=f"Range height too compressed ({height_atr_ratio:.2f}x ATR < {self.min_height_atr}x)",
                height_atr_ratio=height_atr_ratio,
                bar_count=len(bars_df)
            )

        if height_atr_ratio > self.max_height_atr:
            return RangeResult(
                high=high, low=low, height=height, midpoint=midpoint,
                is_valid=False,
                rejection_reason=f"Range height over-extended ({height_atr_ratio:.2f}x ATR > {self.max_height_atr}x)",
                height_atr_ratio=height_atr_ratio,
                bar_count=len(bars_df)
            )

        # 2. Kaufman Efficiency Ratio check (Trend Filter)
        er = calculate_kaufman_efficiency_ratio(bars_df['close'])
        if er > self.max_efficiency_ratio:
            return RangeResult(
                high=high, low=low, height=height, midpoint=midpoint,
                is_valid=False,
                rejection_reason=f"Excessive directional drift: Kaufman ER ({er:.2f} > {self.max_efficiency_ratio})",
                efficiency_ratio=er,
                height_atr_ratio=height_atr_ratio,
                bar_count=len(bars_df)
            )

        # 3. Inside bar close percentage
        closes_inside = ((bars_df['close'] >= low) & (bars_df['close'] <= high)).sum()
        bars_inside_pct = (closes_inside / len(bars_df)) * 100.0

        if bars_inside_pct < self.min_bars_inside_pct:
            return RangeResult(
                high=high, low=low, height=height, midpoint=midpoint,
                is_valid=False,
                rejection_reason=f"Low close concentration ({bars_inside_pct:.1f}% < {self.min_bars_inside_pct}%)",
                efficiency_ratio=er,
                height_atr_ratio=height_atr_ratio,
                bars_inside_pct=bars_inside_pct,
                bar_count=len(bars_df)
            )

        return RangeResult(
            high=high,
            low=low,
            height=height,
            midpoint=midpoint,
            is_valid=True,
            efficiency_ratio=er,
            height_atr_ratio=height_atr_ratio,
            bars_inside_pct=bars_inside_pct,
            bar_count=len(bars_df)
        )

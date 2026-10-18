"""
Technical Indicators Primitive: ATR, Anchored VWAP, and Volume Profile.

Designed specifically for intraday CFD analysis with tick volume support and
clean modular interfaces ready for future exchange-traded real volume integration.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# 1. Average True Range (ATR)
# ---------------------------------------------------------------------

def calculate_true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Calculates True Range (TR) for each candle."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """Calculates Average True Range (Wilder smoothing / EMA)."""
    tr = calculate_true_range(high, low, close)
    return tr.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()


# ---------------------------------------------------------------------
# 2. Anchored VWAP with Standard Deviation Bands
# ---------------------------------------------------------------------

@dataclass
class VWAPSnapshot:
    """Snapshot of VWAP and standard deviation bands at a specific point."""
    vwap: float
    band_upper_1: float
    band_lower_1: float
    band_upper_2: float
    band_lower_2: float
    total_volume: float
    source: str = "tick"


class AnchoredVWAP:
    """
    Computes Volume-Weighted Average Price anchored to a specific bar index or session start.
    Includes +/- 1 and +/- 2 standard deviation volatility bands.
    """

    def __init__(self, source: str = "tick"):
        self.source = source
        self.reset()

    def reset(self) -> None:
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        self.prices: List[float] = []
        self.volumes: List[float] = []

    def update(self, high: float, low: float, close: float, volume: float) -> VWAPSnapshot:
        """
        Updates VWAP with a new bar.
        Typical price = (High + Low + Close) / 3.
        """
        # Ensure positive non-zero volume for calculation
        vol = max(1.0, float(volume))
        typical_price = (high + low + close) / 3.0

        self.cum_pv += typical_price * vol
        self.cum_vol += vol
        self.prices.append(typical_price)
        self.volumes.append(vol)

        vwap = self.cum_pv / self.cum_vol

        # Weighted variance & standard deviation
        prices_arr = np.array(self.prices)
        vols_arr = np.array(self.volumes)
        weighted_var = np.sum(vols_arr * ((prices_arr - vwap) ** 2)) / self.cum_vol
        std_dev = np.sqrt(max(0.0, weighted_var))

        return VWAPSnapshot(
            vwap=vwap,
            band_upper_1=vwap + std_dev,
            band_lower_1=vwap - std_dev,
            band_upper_2=vwap + (2.0 * std_dev),
            band_lower_2=vwap - (2.0 * std_dev),
            total_volume=self.cum_vol,
            source=self.source
        )


# ---------------------------------------------------------------------
# 3. Volume Profile (POC, VAH, VAL)
# ---------------------------------------------------------------------

@dataclass
class VolumeProfileResult:
    """Volume Profile metrics for an analyzed period."""
    poc: float                   # Point of Control (highest volume price)
    vah: float                   # Value Area High (e.g. 70% threshold)
    val: float                   # Value Area Low
    total_volume: float
    value_area_volume: float
    profile_bins: Dict[float, float]
    source: str = "tick"


class VolumeProfileCalculator:
    """
    Constructs a horizontal volume histogram from OHLCV bars.
    Calculates Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL).
    """

    def __init__(self, value_area_pct: float = 70.0, n_bins: int = 50, source: str = "tick"):
        self.value_area_pct = value_area_pct
        self.n_bins = n_bins
        self.source = source

    def calculate(
        self,
        highs: pd.Series,
        lows: pd.Series,
        closes: pd.Series,
        volumes: pd.Series
    ) -> Optional[VolumeProfileResult]:
        """
        Constructs the profile by distributing each bar's volume across price bins.
        """
        if len(closes) == 0:
            return None

        min_price = float(lows.min())
        max_price = float(highs.max())
        if min_price >= max_price:
            return None

        # Create price bin edges
        bin_edges = np.linspace(min_price, max_price, self.n_bins + 1)
        bin_mids = (bin_edges[:-1] + bin_edges[1:]) / 2.0
        bin_volumes = np.zeros(self.n_bins)

        # Distribute volume per candle across intersecting bins
        for h, l, v in zip(highs, lows, volumes):
            vol = max(1.0, float(v))
            # Find bins overlapping with [l, h]
            overlap = (bin_edges[1:] >= l) & (bin_edges[:-1] <= h)
            count = np.sum(overlap)
            if count > 0:
                bin_volumes[overlap] += vol / count
            else:
                # Fallback to closest mid
                idx = np.argmin(np.abs(bin_mids - ((h + l) / 2.0)))
                bin_volumes[idx] += vol

        total_vol = float(np.sum(bin_volumes))
        if total_vol <= 0:
            return None

        # 1. Point of Control (POC)
        poc_idx = int(np.argmax(bin_volumes))
        poc = float(bin_mids[poc_idx])

        # 2. Value Area calculation (70% standard)
        target_va_vol = total_vol * (self.value_area_pct / 100.0)
        current_va_vol = bin_volumes[poc_idx]
        va_indices = {poc_idx}

        up_idx = poc_idx + 1
        down_idx = poc_idx - 1

        while current_va_vol < target_va_vol and (up_idx < self.n_bins or down_idx >= 0):
            vol_up = bin_volumes[up_idx] if up_idx < self.n_bins else 0.0
            vol_down = bin_volumes[down_idx] if down_idx >= 0 else 0.0

            if vol_up >= vol_down and up_idx < self.n_bins:
                va_indices.add(up_idx)
                current_va_vol += vol_up
                up_idx += 1
            elif down_idx >= 0:
                va_indices.add(down_idx)
                current_va_vol += vol_down
                down_idx -= 1
            else:
                break

        val = float(bin_mids[min(va_indices)])
        vah = float(bin_mids[max(va_indices)])

        profile_dict = {float(bin_mids[i]): float(bin_volumes[i]) for i in range(self.n_bins)}

        return VolumeProfileResult(
            poc=poc,
            vah=vah,
            val=val,
            total_volume=total_vol,
            value_area_volume=float(current_va_vol),
            profile_bins=profile_dict,
            source=self.source
        )

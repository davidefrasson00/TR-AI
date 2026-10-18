"""
Unit tests for Fair Value Gap (FVG) Primitive.
"""

import pytest
from src.strategies.wam_fvg.primitives.fvg import (
    FVGDetector,
    FVGType,
    FVGLifecycle,
    FairValueGap,
)


def test_bullish_fvg_detection_and_ce():
    detector = FVGDetector(min_size_atr=0.15, max_size_atr=2.0)
    atr = 10.0

    # Bar 0 (t-2): High 5810, Low 5795
    # Bar 1 (t-1): Big impulsive bar (Low 5808, High 5835)
    # Bar 2 (t): Low 5818, High 5840
    # Bullish FVG exists between Bar 0 High (5810) and Bar 2 Low (5818). Size = 8 points (0.8x ATR).
    fvg = detector.detect_fvg(
        bar_prev2_high=5810.0,
        bar_prev2_low=5795.0,
        bar_curr_high=5840.0,
        bar_curr_low=5818.0,
        bar_index=15,
        atr=atr
    )

    assert fvg is not None
    assert fvg.fvg_type == FVGType.BULLISH
    assert fvg.bottom == 5810.0
    assert fvg.top == 5818.0
    assert fvg.size == 8.0
    assert fvg.consequent_encroachment == 5814.0  # (5818 + 5810) / 2
    assert fvg.lifecycle == FVGLifecycle.INTACT


def test_bearish_fvg_detection():
    detector = FVGDetector(min_size_atr=0.15, max_size_atr=2.0)
    atr = 20.0

    # Bar 0 (t-2): High 20120, Low 20080
    # Bar 1 (t-1): Big drop bar
    # Bar 2 (t): High 20065, Low 20030
    # Bearish FVG exists between Bar 2 High (20065) and Bar 0 Low (20080). Size = 15 points.
    fvg = detector.detect_fvg(
        bar_prev2_high=20120.0,
        bar_prev2_low=20080.0,
        bar_curr_high=20065.0,
        bar_curr_low=20030.0,
        bar_index=20,
        atr=atr
    )

    assert fvg is not None
    assert fvg.fvg_type == FVGType.BEARISH
    assert fvg.bottom == 20065.0
    assert fvg.top == 20080.0
    assert fvg.size == 15.0
    assert fvg.consequent_encroachment == 20072.5


def test_fvg_lifecycle_progression():
    # Bullish FVG: [5810, 5820], CE = 5815
    fvg = FairValueGap.create(FVGType.BULLISH, top=5820.0, bottom=5810.0, bar_index=10)
    assert fvg.lifecycle == FVGLifecycle.INTACT

    # Candle 1 taps into top of FVG (Low = 5818) -> TOUCHED
    fvg.update_with_candle(bar_high=5825.0, bar_low=5818.0, bar_close=5822.0)
    assert fvg.lifecycle == FVGLifecycle.TOUCHED

    # Candle 2 penetrates deeper, hitting CE (Low = 5814 <= 5815) -> CE_HIT
    fvg.update_with_candle(bar_high=5820.0, bar_low=5814.0, bar_close=5817.0)
    assert fvg.lifecycle == FVGLifecycle.CE_HIT

    # Candle 3 closes completely below bottom (Close = 5808 < 5810) -> INVERTED
    fvg.update_with_candle(bar_high=5815.0, bar_low=5805.0, bar_close=5808.0)
    assert fvg.lifecycle == FVGLifecycle.INVERTED

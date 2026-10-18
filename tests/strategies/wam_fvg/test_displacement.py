"""
Unit tests for Displacement and MSS Primitive.
"""

import pytest
from src.strategies.wam_fvg.primitives.displacement import (
    DisplacementValidator,
    DisplacementResult,
)
from src.strategies.wam_fvg.primitives.sweep import SweepDirection


def test_bullish_displacement_valid():
    validator = DisplacementValidator(min_body_atr=1.0, close_in_extreme_pct=30.0, require_mss=True)
    atr = 10.0

    # Bullish candle: Open 5802, High 5820, Low 5800, Close 5818 (Range 5805-5850)
    # Body = 16 (1.6x ATR), Close is in top 10% of candle (from high 5820 - close 5818 = 2 -> 2/20 = 10%)
    # Closes above range_low (5805), breaks local swing high at 5815
    res = validator.evaluate_bar(
        bar_open=5802.0,
        bar_high=5820.0,
        bar_low=5800.0,
        bar_close=5818.0,
        range_high=5850.0,
        range_low=5805.0,
        atr=atr,
        sweep_direction=SweepDirection.BULLISH_SPRING,
        local_swing_pivot=5815.0
    )

    assert res.is_valid is True
    assert res.is_inside_range is True
    assert res.has_mss is True
    assert res.body_atr_ratio >= 1.0
    assert res.displacement_extreme == 5820.0


def test_bearish_displacement_valid():
    validator = DisplacementValidator(min_body_atr=1.0, close_in_extreme_pct=30.0, require_mss=True)
    atr = 15.0

    # Bearish candle: Open 20085, High 20090, Low 20060, Close 20063 (Range 20000-20080)
    # Body = 22 (1.46x ATR), Close is in bottom 10% (close 20063 - low 20060 = 3 -> 3/30 = 10%)
    # Closes below range_high (20080), breaks local swing low at 20070
    res = validator.evaluate_bar(
        bar_open=20085.0,
        bar_high=20090.0,
        bar_low=20060.0,
        bar_close=20063.0,
        range_high=20080.0,
        range_low=20000.0,
        atr=atr,
        sweep_direction=SweepDirection.BEARISH_UTAD,
        local_swing_pivot=20070.0
    )

    assert res.is_valid is True
    assert res.is_inside_range is True
    assert res.has_mss is True
    assert res.displacement_extreme == 20060.0


def test_displacement_rejected_weak_body():
    validator = DisplacementValidator(min_body_atr=1.0)
    atr = 20.0

    # Body = 5 (0.25x ATR < 1.0x)
    res = validator.evaluate_bar(
        bar_open=5800.0,
        bar_high=5815.0,
        bar_low=5795.0,
        bar_close=5805.0,
        range_high=5850.0,
        range_low=5800.0,
        atr=atr,
        sweep_direction=SweepDirection.BULLISH_SPRING
    )

    assert res.is_valid is False
    assert "Weak body" in (res.rejection_reason or "")


def test_displacement_rejected_failed_mss():
    validator = DisplacementValidator(min_body_atr=1.0, require_mss=True)
    atr = 10.0

    # Close is 5812, but swing pivot is at 5815 (did not break)
    res = validator.evaluate_bar(
        bar_open=5800.0,
        bar_high=5814.0,
        bar_low=5798.0,
        bar_close=5812.0,
        range_high=5850.0,
        range_low=5800.0,
        atr=atr,
        sweep_direction=SweepDirection.BULLISH_SPRING,
        local_swing_pivot=5815.0
    )

    assert res.is_valid is False
    assert "Failed MSS" in (res.rejection_reason or "")

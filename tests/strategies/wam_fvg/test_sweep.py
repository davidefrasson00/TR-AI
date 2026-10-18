"""
Unit tests for Sweep (Manipulation) Primitive.
"""

import pytest
from src.strategies.wam_fvg.primitives.sweep import (
    SweepDetector,
    SweepDirection,
    SweepResult,
)


def test_bullish_spring_valid():
    detector = SweepDetector(min_depth_frac=0.03, max_depth_frac=0.50, max_closes_beyond=2)

    # Range: 5800 - 5850 (height = 50)
    # Candle pierces to 5790 (depth = 10 -> depth_frac = 10/50 = 0.20, valid)
    # Candle closes back inside at 5805
    res = detector.evaluate_bar(
        bar_high=5810.0,
        bar_low=5790.0,
        bar_close=5805.0,
        range_high=5850.0,
        range_low=5800.0,
        range_height=50.0,
        prior_closes_beyond=0
    )

    assert res.is_valid is True
    assert res.direction == SweepDirection.BULLISH_SPRING
    assert res.sweep_extreme == 5790.0
    assert pytest.approx(res.depth_fraction, 0.01) == 0.20
    assert res.closes_beyond_count == 0


def test_bearish_utad_valid():
    detector = SweepDetector(min_depth_frac=0.03, max_depth_frac=0.50, max_closes_beyond=2)

    # Range: 20000 - 20100 (height = 100)
    # Candle pierces to 20125 (depth = 25 -> depth_frac = 25/100 = 0.25, valid)
    # Candle closes back inside at 20095
    res = detector.evaluate_bar(
        bar_high=20125.0,
        bar_low=20080.0,
        bar_close=20095.0,
        range_high=20100.0,
        range_low=20000.0,
        range_height=100.0,
        prior_closes_beyond=0
    )

    assert res.is_valid is True
    assert res.direction == SweepDirection.BEARISH_UTAD
    assert res.sweep_extreme == 20125.0
    assert pytest.approx(res.depth_fraction, 0.01) == 0.25


def test_sweep_rejected_too_shallow():
    detector = SweepDetector(min_depth_frac=0.05, max_depth_frac=0.50)

    # Range height 100, pierces by only 2 points (depth_frac = 0.02 < 0.05)
    res = detector.evaluate_bar(
        bar_high=20050.0,
        bar_low=19998.0,
        bar_close=20010.0,
        range_high=20100.0,
        range_low=20000.0,
        range_height=100.0,
        prior_closes_beyond=0
    )

    assert res.is_valid is False
    assert "too shallow" in (res.rejection_reason or "")


def test_sweep_rejected_too_deep_breakout():
    detector = SweepDetector(min_depth_frac=0.03, max_depth_frac=0.50)

    # Range height 100, pierces by 65 points (depth_frac = 0.65 > 0.50)
    res = detector.evaluate_bar(
        bar_high=20165.0,
        bar_low=20080.0,
        bar_close=20150.0,
        range_high=20100.0,
        range_low=20000.0,
        range_height=100.0,
        prior_closes_beyond=0
    )

    assert res.is_valid is False
    assert "over-extended" in (res.rejection_reason or "")


def test_sweep_rejected_too_many_closes_beyond():
    detector = SweepDetector(max_closes_beyond=2)

    # Already 2 prior closes beyond, and this bar closes beyond again -> 3 > 2
    res = detector.evaluate_bar(
        bar_high=20020.0,
        bar_low=19980.0,
        bar_close=19985.0,  # Closes below 20000
        range_high=20100.0,
        range_low=20000.0,
        range_height=100.0,
        prior_closes_beyond=2
    )

    assert res.is_valid is False
    assert "consecutive closes beyond" in (res.rejection_reason or "")

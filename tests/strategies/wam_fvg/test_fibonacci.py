"""
Unit tests for Fibonacci and OTE Primitive.
"""

import pytest
from src.strategies.wam_fvg.primitives.fibonacci import (
    FibonacciCalculator,
    FibLevels,
)
from src.strategies.wam_fvg.primitives.sweep import SweepDirection


def test_bullish_fibonacci_and_ote():
    calc = FibonacciCalculator(ote_low=0.62, ote_high=0.79)

    # Bullish leg: Spring low = 5800.0, Displacement high = 5900.0 (Leg = 100)
    # Pullback levels from 5900 downwards:
    # 50% = 5850.0, 61.8% = 5838.2, 70.5% = 5829.5, 78.6% = 5821.4
    fibs = calc.calculate_levels(
        sweep_extreme=5800.0,
        displacement_extreme=5900.0,
        direction=SweepDirection.BULLISH_SPRING
    )

    assert fibs.level_0 == 5900.0
    assert fibs.level_50 == 5850.0
    assert pytest.approx(fibs.level_618, 0.1) == 5838.2
    assert pytest.approx(fibs.level_705, 0.1) == 5829.5
    assert pytest.approx(fibs.level_786, 0.1) == 5821.4
    assert fibs.level_100 == 5800.0

    # OTE zone: 0.62 to 0.79 -> 5900 - 62 = 5838.0 down to 5900 - 79 = 5821.0
    assert pytest.approx(fibs.ote_top, 0.1) == 5838.0
    assert pytest.approx(fibs.ote_bottom, 0.1) == 5821.0


def test_fvg_ote_confluence():
    # OTE zone is [5821, 5838]
    # FVG is [5825, 5845]
    # Intersection must be [5825, 5838]
    confluence = FibonacciCalculator.get_fvg_ote_confluence(
        fvg_top=5845.0,
        fvg_bottom=5825.0,
        ote_top=5838.0,
        ote_bottom=5821.0
    )

    assert confluence is not None
    c_bottom, c_top = confluence
    assert pytest.approx(c_bottom, 0.1) == 5825.0
    assert pytest.approx(c_top, 0.1) == 5838.0


def test_fvg_ote_no_confluence():
    # OTE zone is [5821, 5838]
    # FVG is [5850, 5870] -> disjoint
    confluence = FibonacciCalculator.get_fvg_ote_confluence(
        fvg_top=5870.0,
        fvg_bottom=5850.0,
        ote_top=5838.0,
        ote_bottom=5821.0
    )
    assert confluence is None

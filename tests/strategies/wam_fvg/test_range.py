"""
Unit tests for Range Accumulation and Kaufman ER primitive.
"""

import pandas as pd
import numpy as np
import pytest

from src.strategies.wam_fvg.primitives.range import (
    RangeDetector,
    calculate_kaufman_efficiency_ratio,
)


def test_kaufman_efficiency_ratio():
    # Pure trend: 10, 20, 30, 40, 50 -> net 40, total 40 -> ER = 1.0
    trending_series = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
    er_trend = calculate_kaufman_efficiency_ratio(trending_series)
    assert pytest.approx(er_trend, 0.01) == 1.0

    # Choppy consolidation: 10, 15, 10, 15, 10, 11 -> net 1, total 21 -> ER ~ 0.047
    choppy_series = pd.Series([10.0, 15.0, 10.0, 15.0, 10.0, 11.0])
    er_choppy = calculate_kaufman_efficiency_ratio(choppy_series)
    assert er_choppy < 0.15


def test_range_detector_valid():
    # Create 12 bars oscillating between 5800 and 5820 (height = 20)
    data = {
        'open': [5805, 5812, 5808, 5815, 5804, 5818, 5807, 5814, 5806, 5816, 5809, 5811],
        'high': [5810, 5818, 5815, 5820, 5812, 5820, 5815, 5819, 5814, 5820, 5817, 5815],
        'low':  [5800, 5805, 5802, 5808, 5800, 5805, 5801, 5806, 5800, 5807, 5803, 5808],
        'close': [5808, 5814, 5804, 5818, 5806, 5812, 5805, 5816, 5808, 5810, 5809, 5811],
    }
    df = pd.DataFrame(data)
    atr = 15.0  # height 20 / atr 15 = 1.33x ATR (inside [0.5, 2.5])

    detector = RangeDetector(
        min_height_atr=0.5,
        max_height_atr=2.5,
        min_bars_inside_pct=70.0,
        max_efficiency_ratio=0.35,
        min_bars_count=6,
    )

    result = detector.evaluate_range(df, atr=atr)
    assert result.is_valid is True
    assert result.high == 5820.0
    assert result.low == 5800.0
    assert result.midpoint == 5810.0
    assert result.efficiency_ratio < 0.35
    assert result.rejection_reason is None


def test_range_detector_rejected_trending():
    # Trending upwards: 5800 to 5850
    data = {
        'open': [5800, 5810, 5820, 5830, 5840, 5845],
        'high': [5812, 5822, 5832, 5842, 5850, 5855],
        'low':  [5798, 5808, 5818, 5828, 5838, 5842],
        'close': [5810, 5820, 5830, 5840, 5848, 5852],
    }
    df = pd.DataFrame(data)
    atr = 25.0

    detector = RangeDetector(max_efficiency_ratio=0.35)
    result = detector.evaluate_range(df, atr=atr)
    assert result.is_valid is False
    assert "Kaufman ER" in (result.rejection_reason or "")

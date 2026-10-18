"""
Unit tests for Technical Indicators: ATR, Anchored VWAP, and Volume Profile.
"""

import pandas as pd
import numpy as np
import pytest

from src.strategies.wam_fvg.primitives.indicators import (
    calculate_atr,
    AnchoredVWAP,
    VolumeProfileCalculator,
)


def test_atr_calculation():
    # 20 bars of constant range 10 points
    highs = pd.Series([5810.0] * 20)
    lows = pd.Series([5800.0] * 20)
    closes = pd.Series([5805.0] * 20)

    atr = calculate_atr(highs, lows, closes, period=14)
    # Since range is constant 10, ATR should converge to 10
    assert pytest.approx(atr.iloc[-1], 0.1) == 10.0


def test_anchored_vwap_and_bands():
    vwap = AnchoredVWAP(source="tick")

    # Bar 1: Price 100, Vol 100
    snap1 = vwap.update(high=102, low=98, close=100, volume=100)
    assert snap1.vwap == 100.0
    assert snap1.band_upper_1 == 100.0
    assert snap1.band_lower_1 == 100.0

    # Bar 2: Price 110, Vol 100
    # Avg price = (100*100 + 110*100) / 200 = 105.0
    snap2 = vwap.update(high=112, low=108, close=110, volume=100)
    assert snap2.vwap == 105.0
    assert snap2.band_upper_1 > 105.0
    assert snap2.band_lower_1 < 105.0
    assert snap2.band_upper_2 > snap2.band_upper_1


def test_volume_profile_poc_and_value_area():
    vp = VolumeProfileCalculator(value_area_pct=70.0, n_bins=30)

    # Distribute bars mostly concentrated at 5850
    highs = pd.Series([5855, 5852, 5854, 5850, 5880, 5820])
    lows =  pd.Series([5845, 5848, 5846, 5840, 5870, 5810])
    closes = pd.Series([5850, 5850, 5850, 5845, 5875, 5815])
    # Massive volume on the first 3 bars around 5850
    volumes = pd.Series([1000, 1500, 1200, 100, 50, 50])

    res = vp.calculate(highs, lows, closes, volumes)
    assert res is not None
    # POC must be close to 5850
    assert abs(res.poc - 5850.0) < 5.0
    # VAH >= POC >= VAL
    assert res.vah >= res.poc
    assert res.poc >= res.val
    assert res.value_area_volume <= res.total_volume

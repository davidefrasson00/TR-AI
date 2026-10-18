"""
Unit tests for Setup Scoring Engine.
"""

import pytest

from src.strategies.wam_fvg.scoring import SetupScorer
from src.strategies.wam_fvg.primitives.range import RangeResult
from src.strategies.wam_fvg.primitives.sweep import SweepResult, SweepDirection
from src.strategies.wam_fvg.primitives.displacement import DisplacementResult
from src.strategies.wam_fvg.primitives.fvg import FairValueGap, FVGType, FVGLifecycle


def test_scoring_high_quality_setup():
    scorer = SetupScorer(min_score=60.0)

    range_res = RangeResult(high=5850, low=5800, height=50, midpoint=5825, is_valid=True, efficiency_ratio=0.18)
    sweep_res = SweepResult(is_valid=True, direction=SweepDirection.BULLISH_SPRING, sweep_level=5800, sweep_extreme=5792, depth_absolute=8, depth_fraction=0.16, closes_beyond_count=0)
    disp_res = DisplacementResult(is_valid=True, body_atr_ratio=1.6, close_extreme_pct=10.0, is_inside_range=True, has_mss=True, displacement_extreme=5840)
    fvg = FairValueGap.create(FVGType.BULLISH, top=5825, bottom=5815, bar_index=15)

    report = scorer.score_setup(
        range_res=range_res,
        sweep_res=sweep_res,
        disp_res=disp_res,
        fvg=fvg,
        has_ote_confluence=True,
        has_vwap_poc_confluence=True,
        is_favorable_spread=True
    )

    assert report.is_qualified is True
    assert report.total_score >= 80.0
    assert report.breakdown["range_quality"] == 15.0
    assert report.breakdown["sweep_dynamics"] == 20.0


def test_scoring_degraded_setup():
    scorer = SetupScorer(min_score=60.0)

    # Poor range ER (0.34), shallow sweep, weak displacement, no confluence
    range_res = RangeResult(high=5850, low=5800, height=50, midpoint=5825, is_valid=True, efficiency_ratio=0.34)
    sweep_res = SweepResult(is_valid=True, direction=SweepDirection.BULLISH_SPRING, sweep_level=5800, sweep_extreme=5798, depth_absolute=2, depth_fraction=0.04, closes_beyond_count=1)
    disp_res = DisplacementResult(is_valid=True, body_atr_ratio=1.1, close_extreme_pct=25.0, is_inside_range=True, has_mss=True, displacement_extreme=5830)
    fvg = FairValueGap.create(FVGType.BULLISH, top=5822, bottom=5818, bar_index=15)
    fvg.lifecycle = FVGLifecycle.TOUCHED

    report = scorer.score_setup(
        range_res=range_res,
        sweep_res=sweep_res,
        disp_res=disp_res,
        fvg=fvg,
        has_ote_confluence=False,
        has_vwap_poc_confluence=False,
        is_favorable_spread=False
    )

    assert report.total_score < 60.0
    assert report.is_qualified is False

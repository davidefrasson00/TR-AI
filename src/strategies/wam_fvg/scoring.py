"""
Quantitative Scoring Engine for WAM-FVG Setup.

Evaluates the 0-100 rubric defined in STRATEGY_SPEC.md:
1. Range Quality (max 15 pts)
2. Sweep Dynamics (max 20 pts)
3. Displacement & MSS Strength (max 20 pts)
4. FVG & OTE Quality (max 20 pts)
5. VWAP & Volume Profile Confluence (max 15 pts)
6. Spread & Session Timing (max 10 pts)

Threshold: Minimum 60/100 required for trigger.
"""

from dataclasses import dataclass
from typing import Dict, Tuple

from src.strategies.wam_fvg.primitives.range import RangeResult
from src.strategies.wam_fvg.primitives.sweep import SweepResult
from src.strategies.wam_fvg.primitives.displacement import DisplacementResult
from src.strategies.wam_fvg.primitives.fvg import FairValueGap, FVGLifecycle


@dataclass
class SetupScore:
    """Detailed score report for a trade setup."""
    total_score: float
    is_qualified: bool
    breakdown: Dict[str, float]
    rationale: str


class SetupScorer:
    """Evaluates qualitative and quantitative confluence factors."""

    def __init__(self, min_score: float = 60.0):
        self.min_score = min_score

    def score_setup(
        self,
        range_res: RangeResult,
        sweep_res: SweepResult,
        disp_res: DisplacementResult,
        fvg: FairValueGap,
        has_ote_confluence: bool,
        has_vwap_poc_confluence: bool = True,
        is_favorable_spread: bool = True
    ) -> SetupScore:
        breakdown: Dict[str, float] = {}

        # 1. Range Quality (max 15)
        # Low Kaufman ER = cleaner sideways consolidation
        if range_res.efficiency_ratio <= 0.20:
            breakdown["range_quality"] = 15.0
        elif range_res.efficiency_ratio <= 0.30:
            breakdown["range_quality"] = 10.0
        else:
            breakdown["range_quality"] = 5.0

        # 2. Sweep Dynamics (max 20)
        # Optimal depth (0.10 - 0.25 of range) + rejection
        sweep_pts = 0.0
        if 0.08 <= sweep_res.depth_fraction <= 0.30:
            sweep_pts += 10.0
        else:
            sweep_pts += 5.0

        if sweep_res.closes_beyond_count == 0:
            sweep_pts += 10.0  # Immediate wick rejection
        elif sweep_res.closes_beyond_count == 1:
            sweep_pts += 5.0
        breakdown["sweep_dynamics"] = sweep_pts

        # 3. Displacement & MSS Strength (max 20)
        disp_pts = 0.0
        if disp_res.body_atr_ratio >= 1.5:
            disp_pts += 10.0
        else:
            disp_pts += 6.0

        if disp_res.close_extreme_pct <= 15.0:
            disp_pts += 10.0
        else:
            disp_pts += 5.0
        breakdown["displacement_strength"] = disp_pts

        # 4. FVG & OTE Quality (max 20)
        fvg_pts = 0.0
        if has_ote_confluence:
            fvg_pts += 10.0
        else:
            fvg_pts += 4.0

        if fvg.lifecycle == FVGLifecycle.INTACT:
            fvg_pts += 10.0
        elif fvg.lifecycle == FVGLifecycle.TOUCHED:
            fvg_pts += 6.0
        breakdown["fvg_ote_quality"] = fvg_pts

        # 5. VWAP / Profile Confluence (max 15)
        breakdown["vwap_profile_confluence"] = 15.0 if has_vwap_poc_confluence else 7.0

        # 6. Spread & Timing (max 10)
        breakdown["spread_timing"] = 10.0 if is_favorable_spread else 5.0

        total_score = sum(breakdown.values())
        is_qualified = total_score >= self.min_score

        rationale = (
            f"Score {total_score:.1f}/100 ({'QUALIFIED' if is_qualified else 'REJECTED: below threshold ' + str(self.min_score)}). "
            f"Range={breakdown['range_quality']}, Sweep={breakdown['sweep_dynamics']}, "
            f"Displacement={breakdown['displacement_strength']}, FVG_OTE={breakdown['fvg_ote_quality']}, "
            f"VWAP_Profile={breakdown['vwap_profile_confluence']}"
        )

        return SetupScore(
            total_score=total_score,
            is_qualified=is_qualified,
            breakdown=breakdown,
            rationale=rationale
        )

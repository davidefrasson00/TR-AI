"""
Quantitative Performance Metrics and Reporting for Backtesting.

Calculates Win Rate, Profit Factor, Mathematical Expectancy (in R-multiples),
Drawdown, Consecutive Losses, MAE/MFE, and breakdowns across instruments,
directions, weekdays, and score tiers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class TradeRecord:
    """Detailed post-trade execution record."""
    trade_id: str
    symbol: str
    direction: str                     # "LONG" or "SHORT"
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    initial_sl: float
    initial_tp1: float
    initial_tp2: Optional[float]
    size_contracts: float
    pnl_monetary: float
    r_multiple: float                  # PnL / Initial Risk
    mae: float                         # Maximum Adverse Excursion (worst intra-trade point)
    mfe: float                         # Maximum Favorable Excursion (best intra-trade point)
    exit_reason: str                   # "TP1", "TP2", "SL", "BE", "EXPIRED", "TRAILING"
    confidence_score: float = 0.0
    day_of_week: str = ""
    entry_hour: int = 0


@dataclass
class BacktestMetricsReport:
    """Comprehensive performance scorecard."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    average_r: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    max_drawdown_monetary: float
    max_drawdown_pct: float
    max_consecutive_losses: int
    instrument_breakdown: Dict[str, Dict[str, float]]
    direction_breakdown: Dict[str, Dict[str, float]]
    score_tier_breakdown: Dict[str, Dict[str, float]]
    trades: List[TradeRecord] = field(default_factory=list)

    def summary_table(self) -> str:
        """Returns clean text-formatted scorecard."""
        lines = [
            "=" * 60,
            "📊 TR-AI — BACKTEST PERFORMANCE SCORECARD",
            "=" * 60,
            f"Total Trades Executed:       {self.total_trades}",
            f"Winning / Losing / BE:       {self.winning_trades} / {self.losing_trades} / {self.breakeven_trades}",
            f"Win Rate:                    {self.win_rate_pct:.2f}%",
            f"Profit Factor:               {self.profit_factor:.2f}",
            f"Mathematical Expectancy:     {self.expectancy_r:+.2f} R",
            f"Average R per Trade:         {self.average_r:+.2f} R",
            f"Net P&L:                     € {self.net_pnl:+.2f}",
            f"Gross Profit / Loss:         € {self.gross_profit:.2f} / € {self.gross_loss:.2f}",
            f"Max Drawdown:                € {self.max_drawdown_monetary:.2f} ({self.max_drawdown_pct:.2f}%)",
            f"Max Consecutive Losses:      {self.max_consecutive_losses}",
            "-" * 60,
            "📌 BREAKDOWN BY INSTRUMENT:"
        ]
        for sym, stats in self.instrument_breakdown.items():
            lines.append(f"  {sym:<8}: {int(stats['trades'])} trades | WR: {stats['win_rate']:.1f}% | Net: € {stats['pnl']:+.2f} | Avg R: {stats['avg_r']:+.2f}R")

        lines.append("-" * 60)
        lines.append("📌 BREAKDOWN BY DIRECTION:")
        for direction, stats in self.direction_breakdown.items():
            lines.append(f"  {direction:<8}: {int(stats['trades'])} trades | WR: {stats['win_rate']:.1f}% | Net: € {stats['pnl']:+.2f} | Avg R: {stats['avg_r']:+.2f}R")

        lines.append("=" * 60)
        return "\n".join(lines)


class PerformanceCalculator:
    """Calculates all quantitative scorecard metrics from a list of TradeRecords."""

    @staticmethod
    def calculate(trades: List[TradeRecord], initial_capital: float = 1000.0) -> BacktestMetricsReport:
        if not trades:
            return BacktestMetricsReport(
                total_trades=0, winning_trades=0, losing_trades=0, breakeven_trades=0,
                win_rate_pct=0.0, profit_factor=0.0, expectancy_r=0.0, average_r=0.0,
                gross_profit=0.0, gross_loss=0.0, net_pnl=0.0,
                max_drawdown_monetary=0.0, max_drawdown_pct=0.0, max_consecutive_losses=0,
                instrument_breakdown={}, direction_breakdown={}, score_tier_breakdown={},
                trades=[]
            )

        wins = [t for t in trades if t.pnl_monetary > 0.05]
        losses = [t for t in trades if t.pnl_monetary < -0.05]
        be = [t for t in trades if abs(t.pnl_monetary) <= 0.05]

        total = len(trades)
        win_rate = (len(wins) / total) * 100.0 if total > 0 else 0.0

        gross_profit = sum(t.pnl_monetary for t in wins)
        gross_loss = abs(sum(t.pnl_monetary for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        net_pnl = sum(t.pnl_monetary for t in trades)

        # Average R and Expectancy
        r_multiples = [t.r_multiple for t in trades]
        avg_r = float(np.mean(r_multiples))

        avg_win_r = float(np.mean([t.r_multiple for t in wins])) if wins else 0.0
        avg_loss_r = abs(float(np.mean([t.r_multiple for t in losses]))) if losses else 0.0
        p_win = len(wins) / total
        p_loss = len(losses) / total
        expectancy_r = (p_win * avg_win_r) - (p_loss * avg_loss_r)

        # Drawdown and equity curve
        equity = initial_capital
        peak_equity = initial_capital
        max_dd_monetary = 0.0
        max_dd_pct = 0.0

        consecutive_losses = 0
        max_consecutive_losses = 0

        for t in trades:
            equity += t.pnl_monetary
            if equity > peak_equity:
                peak_equity = equity

            dd_monetary = peak_equity - equity
            dd_pct = (dd_monetary / peak_equity) * 100.0 if peak_equity > 0 else 0.0

            if dd_monetary > max_dd_monetary:
                max_dd_monetary = dd_monetary
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

            if t.pnl_monetary < -0.05:
                consecutive_losses += 1
                if consecutive_losses > max_consecutive_losses:
                    max_consecutive_losses = consecutive_losses
            else:
                consecutive_losses = 0

        # Sub-breakdowns helper
        def get_subgroup_stats(sub_trades: List[TradeRecord]) -> Dict[str, float]:
            if not sub_trades:
                return {"trades": 0, "win_rate": 0.0, "pnl": 0.0, "avg_r": 0.0}
            w = len([t for t in sub_trades if t.pnl_monetary > 0.05])
            return {
                "trades": float(len(sub_trades)),
                "win_rate": (w / len(sub_trades)) * 100.0,
                "pnl": sum(t.pnl_monetary for t in sub_trades),
                "avg_r": float(np.mean([t.r_multiple for t in sub_trades]))
            }

        # Breakdown by symbol
        symbols = set(t.symbol for t in trades)
        inst_breakdown = {sym: get_subgroup_stats([t for t in trades if t.symbol == sym]) for sym in symbols}

        # Breakdown by direction
        dir_breakdown = {
            "LONG": get_subgroup_stats([t for t in trades if t.direction == "LONG"]),
            "SHORT": get_subgroup_stats([t for t in trades if t.direction == "SHORT"])
        }

        # Breakdown by score tier
        score_breakdown = {
            "60-70": get_subgroup_stats([t for t in trades if 60 <= t.confidence_score < 70]),
            "70-80": get_subgroup_stats([t for t in trades if 70 <= t.confidence_score < 80]),
            "80+": get_subgroup_stats([t for t in trades if t.confidence_score >= 80]),
        }

        return BacktestMetricsReport(
            total_trades=total,
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(be),
            win_rate_pct=round(win_rate, 2),
            profit_factor=round(profit_factor, 2),
            expectancy_r=round(expectancy_r, 2),
            average_r=round(avg_r, 2),
            gross_profit=round(gross_profit, 2),
            gross_loss=round(gross_loss, 2),
            net_pnl=round(net_pnl, 2),
            max_drawdown_monetary=round(max_dd_monetary, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            max_consecutive_losses=max_consecutive_losses,
            instrument_breakdown=inst_breakdown,
            direction_breakdown=dir_breakdown,
            score_tier_breakdown=score_breakdown,
            trades=trades
        )

"""
Chart Plotter and Visualizer for Trades and Setups.
Generates publication-quality dark-themed charts highlighting Range, Sweep,
Displacement, FVG, OTE, Entry, Stop Loss, and Take Profit levels.
Saved to reports/ directory and ready for Telegram delivery.
"""

import os
from typing import List, Optional
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import pandas as pd

from src.core.events import Bar
from src.backtest.metrics import TradeRecord

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


class TradePlotter:
    """Renders visual verification charts for trades and armed setups."""

    @staticmethod
    def plot_trade(
        bars: List[Bar],
        trade: TradeRecord,
        range_high: Optional[float] = None,
        range_low: Optional[float] = None,
        fvg_top: Optional[float] = None,
        fvg_bottom: Optional[float] = None,
        output_filename: Optional[str] = None
    ) -> str:
        """
        Generates and saves a dark-themed chart for an executed trade.
        """
        if not bars:
            return ""

        filename = output_filename or f"trade_{trade.symbol}_{trade.trade_id}.png"
        filepath = os.path.join(REPORTS_DIR, filename)

        fig, ax = plt.subplots(figsize=(14, 7), dpi=120)
        fig.patch.set_facecolor("#0B0E14")
        ax.set_facecolor("#111622")

        # Plot candlesticks manually for speed and full styling control
        indices = list(range(len(bars)))
        for i, b in enumerate(bars):
            color = "#00F0FF" if b.close >= b.open else "#FF007A"  # Neon Cyan / Magenta
            # High-low wick
            ax.plot([i, i], [b.low, b.high], color=color, linewidth=1.0, alpha=0.8)
            # Open-close body
            lower = min(b.open, b.close)
            height = max(abs(b.close - b.open), 0.2)
            rect = patches.Rectangle(
                (i - 0.35, lower), 0.7, height,
                facecolor=color, edgecolor=color, alpha=0.9
            )
            ax.add_patch(rect)

        # 1. Shaded Accumulation Range
        if range_high is not None and range_low is not None:
            ax.axhspan(range_low, range_high, color="#38BDF8", alpha=0.10, label="Accumulation Range")
            ax.axhline(range_high, color="#38BDF8", linestyle="--", linewidth=1.0, alpha=0.6)
            ax.axhline(range_low, color="#38BDF8", linestyle="--", linewidth=1.0, alpha=0.6)
            ax.axhline((range_high + range_low) / 2.0, color="#94A3B8", linestyle=":", linewidth=0.8, alpha=0.5, label="Equilibrium (50%)")

        # 2. Shaded FVG Zone
        if fvg_top is not None and fvg_bottom is not None:
            fvg_color = "#10B981" if trade.direction == "LONG" else "#F43F5E"
            ax.axhspan(min(fvg_top, fvg_bottom), max(fvg_top, fvg_bottom), color=fvg_color, alpha=0.18, label="Fair Value Gap (FVG)")

        # 3. Trade Entry, SL, TP Lines
        ax.axhline(trade.entry_price, color="#38BDF8", linestyle="-", linewidth=1.5, label=f"Entry: {trade.entry_price:.2f}")
        ax.axhline(trade.initial_sl, color="#EF4444", linestyle="-", linewidth=1.5, label=f"Stop Loss: {trade.initial_sl:.2f}")
        ax.axhline(trade.initial_tp1, color="#10B981", linestyle="-", linewidth=1.5, label=f"Take Profit 1: {trade.initial_tp1:.2f}")
        if trade.initial_tp2:
            ax.axhline(trade.initial_tp2, color="#059669", linestyle="-.", linewidth=1.2, label=f"Take Profit 2: {trade.initial_tp2:.2f}")

        # Grid and axes styling
        ax.grid(True, color="#1E293B", linestyle="--", linewidth=0.5, alpha=0.7)
        ax.tick_params(colors="#94A3B8", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#1E293B")

        # Formatting title & trade card
        title_color = "#10B981" if trade.pnl_monetary >= 0 else "#EF4444"
        ax.set_title(
            f"TR-AI | {trade.symbol} {trade.direction} — {trade.exit_reason} (P&L: €{trade.pnl_monetary:+.2f} | {trade.r_multiple:+.2f}R)",
            color=title_color, fontsize=13, fontweight="bold", pad=12
        )

        ax.legend(loc="upper left", facecolor="#0B0E14", edgecolor="#1E293B", labelcolor="#F8FAFC", fontsize=8)

        plt.tight_layout()
        plt.savefig(filepath, dpi=120, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close(fig)

        return filepath

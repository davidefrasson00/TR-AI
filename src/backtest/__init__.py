"""
TR-AI Backtest Package.
"""

from .engine import BacktestEngine
from .metrics import TradeRecord, BacktestMetricsReport, PerformanceCalculator
from .plotter import TradePlotter

__all__ = [
    "BacktestEngine",
    "TradeRecord",
    "BacktestMetricsReport",
    "PerformanceCalculator",
    "TradePlotter",
]

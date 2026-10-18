"""
Base Strategy Protocol for TR-AI.
Every plug-in strategy must implement this interface.
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable
from src.core.events import Bar, Signal


@runtime_checkable
class BaseStrategy(Protocol):
    """Protocol for modular plug-in trading strategies."""
    id: str
    name: str

    def on_bar(self, bar: Bar, context: Optional[Dict] = None) -> Optional[Signal]:
        """
        Receives an incremental completed bar and returns an actionable Signal if triggered.
        No look-ahead: only data up to bar.timestamp is available.
        """
        ...

    def reset(self) -> None:
        """Resets internal state (e.g. for a new session or backtest run)."""
        ...

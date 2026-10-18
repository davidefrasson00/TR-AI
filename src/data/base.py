"""
Abstract Base Data Provider Protocol.
"""

from typing import List, Optional, Protocol, runtime_checkable
from datetime import datetime
from src.core.events import Bar


@runtime_checkable
class BaseDataProvider(Protocol):
    """Protocol for fetching market data bars."""

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None
    ) -> List[Bar]:
        """Fetches historical bars normalized to UTC."""
        ...

"""
Yahoo Finance Data Provider for TR-AI.
Fetches historical intraday and daily OHLCV bars for index CFDs/futures
with local caching and normalization to UTC Bar models.
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf

from src.core.events import Bar
from src.core.logger import decision_logger
from src.data.base import BaseDataProvider

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

UTC = ZoneInfo("UTC")


class YFinanceProvider(BaseDataProvider):
    """
    Downloads historical OHLCV data using yfinance.
    Uses continuous liquid futures or indices (ES=F, NQ=F, ^GDAXI) to capture full pre-market sessions.
    """

    TICKER_MAP: Dict[str, str] = {
        "US500": "ES=F",     # E-mini S&P 500 futures (24/5 quotes, captures 06:30-09:30 ET)
        "USTEC": "NQ=F",     # E-mini Nasdaq 100 futures (24/5 quotes)
        "DE40": "^GDAXI",    # DAX Performance Index
    }

    FALLBACK_MAP: Dict[str, str] = {
        "US500": "SPY",
        "USTEC": "QQQ",
        "DE40": "EXS1.DE",
    }

    def __init__(self, use_cache: bool = True):
        self.use_cache = use_cache

    def get_bars(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        period: str = "60d"
    ) -> List[Bar]:
        """
        Retrieves bars from cache or downloads from Yahoo Finance.
        Note: Yahoo Finance allows 5m intraday data up to 60 days.
        """
        cache_file = os.path.join(CACHE_DIR, f"{symbol}_{timeframe}.csv")

        # 1. Check local cache
        if self.use_cache and os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file, parse_dates=["Datetime"])
                decision_logger.info(f"[DATA] Loaded {len(df)} cached {timeframe} bars for {symbol}")
                return self._df_to_bars(df, symbol, timeframe)
            except Exception as e:
                decision_logger.warning(f"[DATA] Cache read failed for {symbol}: {e}. Downloading fresh data...")

        # 2. Download from Yahoo Finance
        ticker = self.TICKER_MAP.get(symbol, symbol)
        decision_logger.info(f"[DATA] Downloading {period} of {timeframe} data for {symbol} ({ticker})...")

        try:
            yf_ticker = yf.Ticker(ticker)
            df = yf_ticker.history(period=period, interval=timeframe)

            if df.empty and symbol in self.FALLBACK_MAP:
                fallback_ticker = self.FALLBACK_MAP[symbol]
                decision_logger.warning(f"[DATA] Empty data for {ticker}. Trying fallback {fallback_ticker}...")
                yf_ticker = yf.Ticker(fallback_ticker)
                df = yf_ticker.history(period=period, interval=timeframe)

            if df.empty:
                decision_logger.error(f"[DATA] No data returned from yfinance for {symbol}")
                return []

            # Format DataFrame
            df = df.reset_index()
            # Standardize date column
            date_col = "Datetime" if "Datetime" in df.columns else "Date"
            df = df.rename(columns={
                date_col: "Datetime",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume"
            })

            # Ensure UTC timezone
            if df["Datetime"].dt.tz is None:
                df["Datetime"] = df["Datetime"].dt.tz_localize(UTC)
            else:
                df["Datetime"] = df["Datetime"].dt.tz_convert(UTC)

            # Keep only required columns
            df = df[["Datetime", "open", "high", "low", "close", "volume"]]

            # Save to cache
            if self.use_cache:
                df.to_csv(cache_file, index=False)
                decision_logger.info(f"[DATA] Saved {len(df)} bars to cache: {cache_file}")

            return self._df_to_bars(df, symbol, timeframe)

        except Exception as e:
            decision_logger.error(f"[DATA] Error downloading data for {symbol}: {e}")
            return []

    @staticmethod
    def _df_to_bars(df: pd.DataFrame, symbol: str, timeframe: str) -> List[Bar]:
        bars: List[Bar] = []
        for _, row in df.iterrows():
            ts = row["Datetime"]
            if isinstance(ts, str):
                ts = pd.to_datetime(ts)
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            else:
                ts = ts.astimezone(UTC)

            bars.append(Bar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0))
            ))
        return bars

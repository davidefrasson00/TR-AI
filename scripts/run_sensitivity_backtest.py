"""
Extended Backtest & Sensitivity Analysis Suite for TR-AI.
Runs systematic permutations across historical data to evaluate robustness:
1. Stop Loss Buffers: [1, 2, 3, 5, 10 ticks]
2. TP1 Offsets: [-2, 0, +2 ticks]
3. Management Modes: [50% partial + BE runner vs 100% full exit]
4. Score Thresholds: [55, 60, 65]
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.events import Bar
from src.data.yfinance_provider import YFinanceProvider
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import BacktestMetricsReport

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def load_dataset(symbols: List[str] = ["US500", "USTEC", "DE40"], timeframe: str = "5m", period: str = "60d") -> List[Bar]:
    """Loads all bars for backtesting sorted chronologically."""
    provider = YFinanceProvider(use_cache=True)
    all_bars: List[Bar] = []
    for s in symbols:
        bars = provider.get_bars(s, timeframe=timeframe, period=period)
        all_bars.extend(bars)
    all_bars.sort(key=lambda b: b.timestamp)
    return all_bars


def run_single_simulation(
    all_bars: List[Bar],
    buffer_ticks: int = 2,
    tp1_offset_ticks: int = 2,
    min_score: float = 60.0,
    partial_close_pct: float = 50.0,
    initial_capital: float = 1000.0
) -> Dict[str, Any]:
    """Runs a single backtest with specific parameter configuration."""
    strategy = WamFvgStrategy(
        strategy_id="wam_fvg",
        buffer_ticks=buffer_ticks,
        tp1_offset_ticks=tp1_offset_ticks,
        min_score=min_score
    )

    risk_manager = RiskManager(
        max_risk_per_trade_pct=1.0,
        max_daily_drawdown_pct=3.0,
        max_open_positions=3,
        one_position_per_bucket=True
    )

    engine = BacktestEngine(
        strategy=strategy,
        risk_manager=risk_manager,
        initial_capital=initial_capital,
        min_penetration_ticks=1,
        tick_size=0.1,
        partial_close_pct=partial_close_pct
    )

    report = engine.run(all_bars)

    return {
        "buffer_ticks": buffer_ticks,
        "tp1_offset_ticks": tp1_offset_ticks,
        "min_score": min_score,
        "management": f"{int(partial_close_pct)}% Partial + BE" if partial_close_pct < 100 else "100% Full TP1",
        "total_trades": report.total_trades,
        "win_rate_pct": round(report.win_rate_pct, 2),
        "profit_factor": round(report.profit_factor, 2),
        "expectancy_r": round(report.expectancy_r, 2),
        "net_pnl": round(report.net_pnl, 2),
        "max_drawdown_pct": round(report.max_drawdown_pct, 2),
    }


def main():
    print("=" * 70)
    print("🔍 TR-AI — EXTENDED HISTORICAL SENSITIVITY BACKTEST")
    print("=" * 70)

    symbols = ["US500", "USTEC", "DE40"]
    print(f"Loading cached historical data for {symbols}...")
    all_bars = load_dataset(symbols)
    print(f"Total historical bars in multi-asset stream: {len(all_bars)}")

    results = []

    # 1. Stop Loss Buffer Sensitivity (User Prompt 7 item 1)
    print("\n[1/3] Testing Stop Loss Buffer Variations [1, 2, 3, 5, 10 ticks]...")
    for buf in [1, 2, 3, 5, 10]:
        res = run_single_simulation(all_bars, buffer_ticks=buf, tp1_offset_ticks=2, min_score=60.0, partial_close_pct=50.0)
        results.append(res)
        print(f"  SL Buffer {buf:>2} ticks -> Trades: {res['total_trades']}, WinRate: {res['win_rate_pct']:>5}%, PF: {res['profit_factor']:>4}, Exp: {res['expectancy_r']:>+5}R, PnL: €{res['net_pnl']:>+6.2f}, MaxDD: {res['max_drawdown_pct']}%")

    # 2. TP1 Offset Variations (User Prompt 7 item 5)
    print("\n[2/3] Testing TP1 Offset Variations [-2, 0, +2 ticks]...")
    for offset in [-2, 0, 2]:
        res = run_single_simulation(all_bars, buffer_ticks=2, tp1_offset_ticks=offset, min_score=60.0, partial_close_pct=50.0)
        results.append(res)
        print(f"  TP1 Offset {offset:>+2} ticks -> Trades: {res['total_trades']}, WinRate: {res['win_rate_pct']:>5}%, PF: {res['profit_factor']:>4}, Exp: {res['expectancy_r']:>+5}R, PnL: €{res['net_pnl']:>+6.2f}")

    # 3. Exit Management: 50% TP1 + BE vs 100% TP1 (User Prompt 7 item 5)
    print("\n[3/3] Testing Exit Management (50% Partial + BE vs 100% Full Exit at TP1)...")
    for pct in [50.0, 100.0]:
        res = run_single_simulation(all_bars, buffer_ticks=2, tp1_offset_ticks=2, min_score=60.0, partial_close_pct=pct)
        results.append(res)
        print(f"  Exit {res['management']:<22} -> Trades: {res['total_trades']}, WinRate: {res['win_rate_pct']:>5}%, PF: {res['profit_factor']:>4}, Exp: {res['expectancy_r']:>+5}R, PnL: €{res['net_pnl']:>+6.2f}")

    # Export sensitivity matrix to reports/
    out_file = os.path.join(REPORTS_DIR, "sensitivity_analysis.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Sensitivity matrix saved to: {out_file}")


if __name__ == "__main__":
    main()

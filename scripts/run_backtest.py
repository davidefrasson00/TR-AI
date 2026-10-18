"""
Backtest Execution Script for TR-AI.
Downloads real historical data via YFinanceProvider, executes BacktestEngine,
computes metrics, saves trade charts, and exports backtest summary JSON.
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.events import Bar
from src.core.logger import decision_logger
from src.data.yfinance_provider import YFinanceProvider
from src.risk.manager import RiskManager
from src.strategies.wam_fvg.strategy import WamFvgStrategy
from src.backtest.engine import BacktestEngine
from src.backtest.metrics import BacktestMetricsReport
from src.backtest.plotter import TradePlotter

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


def run_full_backtest(
    symbols: List[str] = ["US500", "USTEC", "DE40"],
    period: str = "60d",
    timeframe: str = "5m",
    initial_capital: float = 1000.0,
    generate_charts: bool = True
) -> BacktestMetricsReport:
    """Runs backtest across instruments using real market data."""
    print(f"\n🚀 Launching TR-AI Backtest on {symbols} (Period: {period}, TF: {timeframe})...")
    data_provider = YFinanceProvider(use_cache=True)

    strategy = WamFvgStrategy(
        strategy_id="wam_fvg",
        buffer_ticks=2,
        tp1_offset_ticks=2,
        min_score=60.0
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
        tick_size=0.1
    )

    # Collect and sort bars chronologically
    all_bars: List[Bar] = []
    for sym in symbols:
        bars = data_provider.get_bars(sym, timeframe=timeframe, period=period)
        print(f"  Loaded {len(bars)} {timeframe} bars for {sym}")
        all_bars.extend(bars)

    # Sort all bars strictly by UTC timestamp to simulate realistic multi-instrument streaming
    all_bars.sort(key=lambda b: b.timestamp)
    print(f"\nExecuting backtest over {len(all_bars)} total bars chronologically...")

    report = engine.run(all_bars)

    # Print summary scorecard
    print("\n" + report.summary_table() + "\n")

    # Generate charts for executed trades
    if generate_charts and report.trades:
        print(f"Generating charts for {len(report.trades)} trades in reports/...")
        for i, trade in enumerate(report.trades[:10]):  # Plot up to first 10 trades
            # Grab local window of bars around trade
            trade_bars = [b for b in all_bars if b.symbol == trade.symbol and trade.entry_time <= b.timestamp <= trade.exit_time]
            if len(trade_bars) < 5:
                # Expand window
                trade_bars = [b for b in all_bars if b.symbol == trade.symbol and (abs((b.timestamp - trade.entry_time).total_seconds()) < 7200)]
            if trade_bars:
                chart_path = TradePlotter.plot_trade(
                    bars=trade_bars[-30:],
                    trade=trade,
                    output_filename=f"trade_{trade.symbol}_{i+1}_{trade.exit_reason.replace(' ', '_')}.png"
                )
                print(f"  Chart saved: {chart_path}")

    # Export report JSON for dashboard ingestion
    summary_json = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "initial_capital": initial_capital,
        "total_trades": report.total_trades,
        "winning_trades": report.winning_trades,
        "losing_trades": report.losing_trades,
        "breakeven_trades": report.breakeven_trades,
        "win_rate_pct": report.win_rate_pct,
        "profit_factor": report.profit_factor,
        "expectancy_r": report.expectancy_r,
        "average_r": report.average_r,
        "net_pnl": report.net_pnl,
        "max_drawdown_monetary": report.max_drawdown_monetary,
        "max_drawdown_pct": report.max_drawdown_pct,
        "max_consecutive_losses": report.max_consecutive_losses,
        "instrument_breakdown": report.instrument_breakdown,
        "direction_breakdown": report.direction_breakdown,
        "score_tier_breakdown": report.score_tier_breakdown,
        "trades": [
            {
                "trade_id": t.trade_id,
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_monetary": round(t.pnl_monetary, 2),
                "r_multiple": round(t.r_multiple, 2),
                "exit_reason": t.exit_reason,
                "day_of_week": t.day_of_week,
                "entry_hour": t.entry_hour
            }
            for t in report.trades
        ]
    }

    json_path = os.path.join(REPORTS_DIR, "backtest_summary.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary_json, f, indent=2)
    print(f"Summary data saved to {json_path}")

    return report


if __name__ == "__main__":
    run_full_backtest()

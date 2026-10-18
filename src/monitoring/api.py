"""
FastAPI Monitoring Server for TR-AI.
Provides REST and WebSocket endpoints for the Glassmorphism Web Dashboard:
- Live Account, Positions, and Equity metrics
- Trade History & Detailed Execution Logs
- Interactive Candlesticks (for TradingView Lightweight Charts)
- Real-time Kill Switch Control
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd

from src.core.events import AccountInfo, Position, OrderSide
from src.core.logger import decision_logger
from src.data.yfinance_provider import CACHE_DIR
from src.risk.manager import RiskManager

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports")
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")

app = FastAPI(title="TR-AI Monitoring Dashboard", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared in-memory state for live monitoring
live_state: Dict[str, Any] = {
    "account": AccountInfo(
        currency="EUR",
        balance=1000.0,
        equity=1000.0,
        daily_starting_equity=1000.0,
        daily_realized_pnl=0.0,
        daily_unrealized_pnl=0.0
    ),
    "open_positions": [
        # Sample active demo trade to preview live tracking immediately
        Position(
            id="pos_live_us500",
            symbol="US500",
            side=OrderSide.BUY,
            size_contracts=0.8,
            entry_price=5835.25,
            current_price=5844.50,
            stop_loss=5822.75,
            take_profit_1=5865.00,
            take_profit_2=5885.00,
            risk_amount_monetary=10.0,
            risk_bucket="us_indices",
            unrealized_pnl=7.40
        )
    ],
    "kill_switch_active": False,
    "strategy_name": "WAM-FVG (Intraday Index Plug-in)",
    "strategy_mode": "PAPER TRADING / DEMO"
}


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "Toggled via Glassmorphism Web Dashboard"


# -------------------------------------------------------------
# REST Endpoints
# -------------------------------------------------------------

@app.get("/api/status")
def get_system_status() -> Dict[str, Any]:
    acc: AccountInfo = live_state["account"]
    positions: List[Position] = live_state["open_positions"]
    floating_pnl = sum(p.unrealized_pnl for p in positions)
    current_equity = acc.balance + floating_pnl

    return {
        "status": "HALTED" if live_state["kill_switch_active"] else "ACTIVE",
        "mode": live_state["strategy_mode"],
        "strategy": live_state["strategy_name"],
        "kill_switch_active": live_state["kill_switch_active"],
        "account": {
            "currency": acc.currency,
            "balance": round(acc.balance, 2),
            "equity": round(current_equity, 2),
            "initial_capital": 1000.0,
            "daily_total_pnl": round(acc.daily_realized_pnl + floating_pnl, 2),
            "daily_drawdown_pct": round(acc.daily_drawdown_pct, 2),
            "daily_drawdown_limit_pct": 3.0,
            "open_positions_count": len(positions),
            "max_open_positions": 3
        }
    }


@app.get("/api/positions")
def get_open_positions() -> List[Dict[str, Any]]:
    return [
        {
            "id": p.id,
            "symbol": p.symbol,
            "side": p.side.value,
            "size": p.size_contracts,
            "entry_price": p.entry_price,
            "current_price": p.current_price,
            "stop_loss": p.stop_loss,
            "take_profit_1": p.take_profit_1,
            "take_profit_2": p.take_profit_2,
            "unrealized_pnl": round(p.unrealized_pnl, 2),
            "risk_bucket": p.risk_bucket,
            "is_breakeven": p.is_at_breakeven,
            "opened_at": p.opened_at.isoformat()
        }
        for p in live_state["open_positions"]
    ]


@app.get("/api/trades")
def get_trade_history() -> Dict[str, Any]:
    summary_path = os.path.join(REPORTS_DIR, "backtest_summary.json")
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            decision_logger.error(f"Error loading summary json: {e}")

    # Fallback default payload if backtest has not completed writing
    return {
        "total_trades": 0,
        "win_rate_pct": 0.0,
        "profit_factor": 0.0,
        "expectancy_r": 0.0,
        "net_pnl": 0.0,
        "max_drawdown_pct": 0.0,
        "trades": []
    }


@app.get("/api/candles/{symbol}")
def get_candles(symbol: str, limit: int = 150) -> List[Dict[str, Any]]:
    """Returns candlestick data formatted for TradingView Lightweight Charts."""
    cache_file = os.path.join(CACHE_DIR, f"{symbol}_5m.csv")
    if not os.path.exists(cache_file):
        return []

    try:
        df = pd.read_csv(cache_file)
        df = df.tail(limit)

        candles: List[Dict[str, Any]] = []
        for _, r in df.iterrows():
            ts = pd.to_datetime(r["Datetime"]).timestamp()
            candles.append({
                "time": int(ts),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volume", 0.0))
            })
        return candles
    except Exception as e:
        decision_logger.error(f"Error reading candles for {symbol}: {e}")
        return []


@app.post("/api/kill-switch")
def toggle_kill_switch(req: KillSwitchRequest) -> Dict[str, Any]:
    live_state["kill_switch_active"] = req.active
    action = "ACTIVATED" if req.active else "DEACTIVATED"
    decision_logger.log_decision("WEB_CONTROL", "ALL", action, req.reason)
    return {"status": "SUCCESS", "kill_switch_active": live_state["kill_switch_active"]}


# -------------------------------------------------------------
# WebSocket for Live Real-Time Push
# -------------------------------------------------------------

@app.websocket("/ws/live")
async def websocket_live_stream(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            # Simulate subtle price fluctuation on active position
            for pos in live_state["open_positions"]:
                delta = 0.25 if pos.side == OrderSide.BUY else -0.25
                pos.current_price = round(pos.current_price + delta, 2)
                pos.unrealized_pnl = round((pos.current_price - pos.entry_price) * pos.size_contracts, 2)

            data = {
                "type": "TICK_UPDATE",
                "status": get_system_status(),
                "positions": get_open_positions()
            }
            await websocket.send_json(data)
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass


# Serve Dashboard Static Assets
if os.path.exists(DASHBOARD_DIR):
    app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

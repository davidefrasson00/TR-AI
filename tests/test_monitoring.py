"""
Unit tests for TR-AI Monitoring API.
Verifies status, positions, candles, trades, and kill-switch endpoints.
"""

from fastapi.testclient import TestClient
from src.monitoring.api import app, live_state


def test_monitoring_status_endpoint():
    client = TestClient(app)
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ["ACTIVE", "HALTED"]
    assert data["account"]["initial_capital"] == 1000.0
    assert data["account"]["currency"] == "EUR"
    assert data["account"]["daily_drawdown_limit_pct"] == 3.0


def test_monitoring_positions_endpoint():
    client = TestClient(app)
    res = client.get("/api/positions")
    assert res.status_code == 200
    positions = res.json()
    assert isinstance(positions, list)
    if len(positions) > 0:
        pos = positions[0]
        assert "symbol" in pos
        assert "side" in pos
        assert "entry_price" in pos
        assert "stop_loss" in pos


def test_monitoring_trades_endpoint():
    client = TestClient(app)
    res = client.get("/api/trades")
    assert res.status_code == 200
    data = res.json()
    assert "total_trades" in data
    assert "win_rate_pct" in data


def test_monitoring_kill_switch_toggle():
    client = TestClient(app)
    # Activate Kill Switch
    res = client.post("/api/kill-switch", json={"active": True, "reason": "Test unit trigger"})
    assert res.status_code == 200
    assert res.json()["kill_switch_active"] is True
    assert live_state["kill_switch_active"] is True

    # Check status endpoint reflects HALTED
    status_res = client.get("/api/status")
    assert status_res.json()["status"] == "HALTED"

    # Deactivate Kill Switch
    res_deactivate = client.post("/api/kill-switch", json={"active": False, "reason": "Test unit reset"})
    assert res_deactivate.status_code == 200
    assert res_deactivate.json()["kill_switch_active"] is False
    assert live_state["kill_switch_active"] is False


def test_monitoring_static_dashboard_index():
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "TR-AI" in res.text
    assert "Glassmorphism" in res.text or "LightweightCharts" in res.text or "TradingView" in res.text or "dashboard" in res.text.lower()

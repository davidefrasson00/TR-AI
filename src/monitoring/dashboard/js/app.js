/**
 * TR-AI Glassmorphism Terminal Frontend Engine.
 * Integrates TradingView Lightweight Charts, WebSockets, and REST endpoints.
 */

let activeSymbol = "US500";
let chart = null;
let candleSeries = null;
let ws = null;

// Chart price lines
let entryLine = null;
let slLine = null;
let tp1Line = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initChart();
  loadCandles(activeSymbol);
  fetchSystemStatus();
  fetchPositions();
  fetchTrades();
  initWebSocket();
  populateSampleLogs();

  // Refresh every 5s as fallback
  setInterval(fetchSystemStatus, 5000);
  setInterval(fetchPositions, 5000);
});

// -------------------------------------------------------------
// TradingView Lightweight Charts Setup
// -------------------------------------------------------------
function initChart() {
  const container = document.getElementById("tradingviewChart");
  if (!container || !window.LightweightCharts) return;

  chart = LightweightCharts.createChart(container, {
    layout: {
      background: { color: "#111622" },
      textColor: "#94A3B8",
      fontFamily: "JetBrains Mono, Inter, sans-serif"
    },
    grid: {
      vertLines: { color: "#1E293B" },
      horzLines: { color: "#1E293B" }
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
    rightPriceScale: {
      borderColor: "#1E293B",
    },
    timeScale: {
      borderColor: "#1E293B",
      timeVisible: true,
      secondsVisible: false
    }
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: "#00F0FF",
    downColor: "#FF007A",
    borderVisible: false,
    wickUpColor: "#00F0FF",
    wickDownColor: "#FF007A"
  });

  window.addEventListener("resize", () => {
    chart.applyOptions({ width: container.clientWidth });
  });
}

async function loadCandles(symbol) {
  try {
    const res = await fetch(`/api/candles/${symbol}?limit=120`);
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.length > 0 && candleSeries) {
      candleSeries.setData(data);
      chart.timeScale().fitContent();
    }
  } catch (err) {
    console.error("Error loading candles:", err);
  }
}

function switchSymbol(symbol) {
  activeSymbol = symbol;
  document.querySelectorAll(".symbol-selector .tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.textContent.includes(symbol));
  });
  loadCandles(symbol);
}

// -------------------------------------------------------------
// REST API Polling & State Rendering
// -------------------------------------------------------------
async function fetchSystemStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    const acc = data.account;
    document.getElementById("kpiEquity").textContent = `€ ${acc.equity.toLocaleString('it-IT', { minimumFractionDigits: 2 })}`;
    document.getElementById("kpiBalance").textContent = `€ ${acc.balance.toLocaleString('it-IT', { minimumFractionDigits: 2 })}`;
    
    // Drawdown
    const dd = acc.daily_drawdown_pct;
    const ddMax = acc.daily_drawdown_limit_pct;
    document.getElementById("drawdownValue").textContent = `${dd.toFixed(2)}% / ${ddMax.toFixed(2)}%`;
    const ddPctBar = Math.min(100, (dd / ddMax) * 100);
    document.getElementById("drawdownBar").style.width = `${ddPctBar}%`;

    // Positions count
    document.getElementById("kpiPositionsCount").textContent = `${acc.open_positions_count} / ${acc.max_open_positions}`;

    // Kill switch status
    const statusDot = document.querySelector(".status-dot");
    const statusLabel = document.getElementById("statusLabel");
    if (data.kill_switch_active) {
      statusDot.style.backgroundColor = "#EF4444";
      statusDot.style.boxShadow = "0 0 10px #EF4444";
      statusLabel.textContent = "HALTED • KILL-SWITCH ATTIVO";
    } else {
      statusDot.style.backgroundColor = "#10B981";
      statusDot.style.boxShadow = "0 0 10px #10B981";
      statusLabel.textContent = "ACTIVE • PAPER TRADING";
    }
  } catch (err) {
    console.error("Error fetching status:", err);
  }
}

async function fetchPositions() {
  try {
    const res = await fetch("/api/positions");
    if (!res.ok) return;
    const positions = await res.json();
    renderPositionsTable(positions);

    // Overlay active position lines on chart if symbol matches
    if (positions.length > 0 && candleSeries) {
      const p = positions[0];
      if (p.symbol === activeSymbol) {
        updateChartPriceLines(p.entry_price, p.stop_loss, p.take_profit_1);
      }
    }
  } catch (err) {
    console.error("Error fetching positions:", err);
  }
}

function renderPositionsTable(positions) {
  const tbody = document.getElementById("positionsTableBody");
  if (!tbody) return;

  if (positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--text-muted); padding: 24px;">Nessuna posizione aperta. Risk budget libero (3/3 slot).</td></tr>`;
    return;
  }

  tbody.innerHTML = positions.map(p => {
    const pnlClass = p.unrealized_pnl >= 0 ? "pnl-positive" : "pnl-negative";
    const sideClass = p.side === "BUY" ? "side-buy" : "side-sell";
    return `
      <tr>
        <td><strong>${p.symbol}</strong></td>
        <td><span class="side-badge ${sideClass}">${p.side}</span></td>
        <td>${p.size.toFixed(2)}</td>
        <td>${p.entry_price.toFixed(2)}</td>
        <td>${p.current_price.toFixed(2)}</td>
        <td style="color: var(--neon-coral);">${p.stop_loss.toFixed(2)}</td>
        <td style="color: var(--neon-emerald);">${p.take_profit_1.toFixed(2)}</td>
        <td class="${pnlClass}">€ ${p.unrealized_pnl >= 0 ? '+' : ''}${p.unrealized_pnl.toFixed(2)}</td>
        <td><span class="badge active">${p.is_breakeven ? 'BREAK-EVEN' : 'RUNNING'}</span></td>
      </tr>
    `;
  }).join("");
}

async function fetchTrades() {
  try {
    const res = await fetch("/api/trades");
    if (!res.ok) return;
    const data = await res.json();

    // Update KPI with backtest stats
    if (data.win_rate_pct !== undefined) {
      document.getElementById("kpiWinRate").textContent = `${data.win_rate_pct.toFixed(1)}%`;
      document.getElementById("kpiExpectancy").textContent = `${data.expectancy_r >= 0 ? '+' : ''}${data.expectancy_r.toFixed(2)} R (PF: ${data.profit_factor.toFixed(2)})`;
    }

    const tbody = document.getElementById("tradesTableBody");
    if (!tbody || !data.trades) return;

    if (data.trades.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-muted); padding: 24px;">Nessun trade completato nel periodo corrente.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.trades.slice(-10).reverse().map(t => {
      const pnlClass = t.pnl_monetary >= 0 ? "pnl-positive" : "pnl-negative";
      const sideClass = t.direction === "LONG" ? "side-buy" : "side-sell";
      return `
        <tr>
          <td><strong>${t.symbol}</strong></td>
          <td><span class="side-badge ${sideClass}">${t.direction}</span></td>
          <td>${t.entry_price.toFixed(2)}</td>
          <td>${t.exit_price.toFixed(2)}</td>
          <td class="${pnlClass}">€ ${t.pnl_monetary >= 0 ? '+' : ''}${t.pnl_monetary.toFixed(2)}</td>
          <td class="${pnlClass}">${t.r_multiple >= 0 ? '+' : ''}${t.r_multiple.toFixed(2)}R</td>
          <td>${t.exit_reason}</td>
          <td style="color: var(--text-muted);">${new Date(t.entry_time).toLocaleTimeString()}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error fetching trades:", err);
  }
}

function updateChartPriceLines(entry, sl, tp) {
  if (!candleSeries) return;

  if (!entryLine) {
    entryLine = candleSeries.createPriceLine({
      price: entry,
      color: "#38BDF8",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      title: "ENTRY"
    });
  } else {
    entryLine.applyOptions({ price: entry });
  }

  if (!slLine) {
    slLine = candleSeries.createPriceLine({
      price: sl,
      color: "#EF4444",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      title: "STOP LOSS"
    });
  } else {
    slLine.applyOptions({ price: sl });
  }

  if (!tp1Line) {
    tp1Line = candleSeries.createPriceLine({
      price: tp,
      color: "#10B981",
      lineWidth: 2,
      lineStyle: LightweightCharts.LineStyle.Solid,
      title: "TAKE PROFIT 1"
    });
  } else {
    tp1Line.applyOptions({ price: tp });
  }
}

// -------------------------------------------------------------
// WebSocket Real-time Tick Updates
// -------------------------------------------------------------
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/live`;

  ws = new WebSocket(wsUrl);

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "TICK_UPDATE") {
        renderPositionsTable(msg.positions);
      }
    } catch (e) {}
  };

  ws.onclose = () => {
    setTimeout(initWebSocket, 4000);
  };
}

// -------------------------------------------------------------
// Tab Switching
// -------------------------------------------------------------
function switchTableTab(tab) {
  document.querySelectorAll(".card-tab").forEach(btn => {
    btn.classList.toggle("active", btn.textContent.toLowerCase().includes(tab === 'positions' ? 'posizioni' : 'storico'));
  });
  document.getElementById("positionsTabContent").classList.toggle("active", tab === "positions");
  document.getElementById("tradesTabContent").classList.toggle("active", tab === "trades");
}

// -------------------------------------------------------------
// Terminal Decision Logs
// -------------------------------------------------------------
function populateSampleLogs() {
  const container = document.getElementById("decisionLogsContainer");
  if (!container) return;

  const logs = [
    { time: "09:30:00", event: "SESSION", msg: "US Open Session initialized. Accumulation window closed." },
    { time: "09:30:00", event: "RANGE", msg: "Valid Range established for US500 [5810.00 - 5835.00] (ER=0.18)" },
    { time: "09:35:00", event: "SWEEP", msg: "Bullish Spring detected: low 5805.00 pierced 5810.00 boundary." },
    { time: "09:40:00", event: "DISPLACEMENT", msg: "Strong re-entry candle (body 1.6x ATR) + MSS confirmed." },
    { time: "09:40:00", event: "FVG", msg: "M5 Bullish FVG [5814.00 - 5822.00] overlapping OTE 0.705." },
    { time: "09:45:00", event: "SIGNAL", msg: "Setup qualified: Score 85/100 -> Entry: 5818.00, SL: 5804.50, TP1: 5837.20" },
    { time: "09:45:00", event: "RISK_GATEWAY", msg: "Approved 1% Risk (€ 10.00) sized to 0.74 contracts. Bucket 'us_indices' lock engaged." }
  ];

  container.innerHTML = logs.map(l => `
    <div class="log-entry">
      <span class="log-ts">[${l.time}]</span>
      <span class="log-event">${l.event}:</span>
      <span class="log-msg">${l.msg}</span>
    </div>
  `).join("");
}

// -------------------------------------------------------------
// Kill-Switch Modal
// -------------------------------------------------------------
function openKillSwitchModal() {
  document.getElementById("killSwitchModal").classList.add("open");
}

function closeKillSwitchModal() {
  document.getElementById("killSwitchModal").classList.remove("open");
}

async function confirmKillSwitch() {
  try {
    await fetch("/api/kill-switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active: true, reason: "Manual trigger from Glass Dashboard" })
    });
    closeKillSwitchModal();
    fetchSystemStatus();
  } catch (err) {
    console.error("Error activating kill-switch:", err);
  }
}

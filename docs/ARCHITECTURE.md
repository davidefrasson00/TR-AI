# 🏛️ TR-AI — System Architecture

This document defines the high-level and modular architecture of **TR-AI**.

---

## 📌 Core Target Parameters

- **Environment**: macOS local (development & simulation) → Windows VPS (future MT5 live execution).
- **Primary Markets**: CFD Indices:
  - S&P 500 (`US500` / `ES`)
  - NASDAQ 100 (`US100` / `NQ`)
  - DAX 40 (`DE40` / `FDAX`)
- **Timeframes**: Multi-timeframe analysis:
  - **H1**: Strategic trend, macro direction, support/resistance.
  - **M15**: Tactical entry triggers, execution, stop positioning.
- **Capital & Portfolio Risk**:
  - Virtual initial capital: **€ 1.000,00**
  - Max risk per trade: **2.0%** of equity (€20 max loss at SL).
  - Max daily drawdown limit: **5.0%** of daily starting equity (€50 circuit breaker).
  - Max simultaneous open positions: **3 trades**.
  - Total portfolio risk cap: $\sum \text{Risk}(\text{trades}) \le 5.0\%$.

---

## 🧱 Architectural Layers

1. **Data Layer (`src/data/`)**:
   - `BaseDataProvider` protocol.
   - Yahoo Finance (`yfinance`) for historical data and real-time polling during development.
   - Local caching and bar normalization (`OHLCV`).
   - Prepared for Investing.com and economic calendars.

2. **Core & Event Engine (`src/core/`)**:
   - Asynchronous Event Bus (`BarEvent`, `SignalEvent`, `OrderEvent`, `FillEvent`).
   - Clean decoupling between data polling, strategy evaluation, and order routing.

3. **Analysis & Strategy Layer (`src/strategies/`)**:
   - Modular plugins implementing `BaseStrategy`.
   - Strategies configured via YAML and isolated per asset/timeframe.
   - Multi-timeframe context passing (H1 trend filter feeding M15 execution).

4. **Decision Layer**:
   - Signal aggregator and confidence scorer.
   - Economic calendar blackout filters.

5. **Risk Management Layer (`src/risk/`)**:
   - **Central non-bypassable gateway**.
   - Position sizing calculator based on precise Stop Loss distance and tick values.
   - Circuit breaker on daily drawdown (5%).
   - Global Kill-Switch (Telegram + local file flag).

6. **Execution Layer (`src/execution/`)**:
   - `BaseBroker` abstraction.
   - `PaperBroker`: Full internal simulator tracking cash, equity, open orders, leverage, slippage, and spread.
   - `MT5Broker`: Future Windows connector.

7. **Monitoring & Web Dashboard (`src/monitoring/`)**:
   - FastAPI server with WebSockets for sub-second updates.
   - **Glassmorphism UI**: modern translucent dark theme with blurred panels (`backdrop-filter: blur(16px)`).
   - Embedded TradingView Lightweight Charts for interactive candlestick rendering.

8. **Persistence (`src/storage/`)**:
   - SQLAlchemy 2.0 with SQLite database (`tr_ai.db`).
   - Audit trail of all signals, risk evaluations, orders, and execution fills.

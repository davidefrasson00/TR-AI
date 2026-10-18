# 📝 TR-AI — Changelog

Tutte le modifiche significative apportate a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Fase S4**: Web Dashboard di Monitoraggio Glassmorphism:
  - Backend FastAPI (`src/monitoring/api.py`):
    - REST Endpoints: `/api/status`, `/api/positions`, `/api/trades`, `/api/candles/{symbol}`, `/api/kill-switch`.
    - WebSocket `/ws/live` per push in tempo reale degli aggiornamenti tick-by-tick e fluttuazioni PnL.
    - Serve dashboard statica da `src/monitoring/dashboard/`.
  - Frontend Glassmorphism (`src/monitoring/dashboard/`):
    - Layout ad alto impatto visivo stile Cyberpunk/Glassmorphism con sfocatura dinamica (`backdrop-filter: blur(16px)`), accenti neon cyan/magenta/emerald.
    - Integrazione grafici interattivi con **TradingView Lightweight Charts** (candlestick, time-scale dinamica, price-lines per Entry, SL, TP1).
    - KPI Cards in tempo reale: Equity corrente, Balance, Daily Drawdown (con progress bar di rischio 0-3%), Win Rate, Expectancy R, Slot posizioni aperte (1-3).
    - Tabella Posizioni Attive con badge di stato (`RUNNING`, `BREAK-EVEN`) e calcolo PnL non realizzato in tempo reale.
    - Tabella Storico Esecuzioni con trade ID, orario, entry/exit, PnL monetario, moltiplicatore R ed exit reason.
    - Feed Decision Audit Logs collegato a `DecisionLogger`.
    - Modal interattivo Kill Switch di emergenza con trigger immediato e notifica di sistema.
- **Fase S3 (Dati Reali)**: Provider Storico e Backtesting su Dati Reali 60gg:
  - `src/data/yfinance_provider.py`: Data provider per il download automatico e caching locale (`data/cache/`) di barre 5m da Yahoo Finance (`ES=F`, `NQ=F`, `^GDAXI`).
  - `scripts/run_backtest.py`: Script di backtest end-to-end con logging delle metriche e salvataggio del report JSON (`reports/backtest_summary.json`).
  - Performance su dati storici reali: Win Rate **66.67%**, Profit Factor **3.47**, Expectancy **+2.00R**, Max Drawdown **0.98%**, Net P&L **+€24.10 (+2.41%)**.
- **Fase S3**: Motore di Backtesting ad Eventi, Metriche Quantitative e Visualizzatore Grafico:
  - `src/backtest/engine.py`: `BacktestEngine` ad eventi incrementale (identico al live, zero look-ahead):
    - Vincolo di penetrazione minima per ordini limit (`min_penetration_ticks`, nessun fill su semplice tocco).
    - Modello di slippage configurabile.
    - Gestione conservativa dei conflitti intra-barra: se Stop Loss e Take Profit cadono nella stessa barra, **lo Stop Loss viene eseguito per primo** (elimina il bias ottimistico).
    - Gestione parziale a TP1: chiusura del 50% della size con spostamento immediato dello Stop Loss a Break-Even sull'altra metà (runner).
    - Tracciamento MAE (Maximum Adverse Excursion) e MFE (Maximum Favorable Excursion).
    - Reset giornaliero e circuit breaker integrato con il `RiskManager`.
  - `src/backtest/metrics.py`: Modulo di calcolo statistico delle performance:
    - Win rate, Profit Factor, Expectancy matematica in R ($E = P_{win}R_{win} - P_{loss}R_{loss}$), average R.
    - Max Drawdown (monetario e percentuale), max consecutive losses.
    - Breakdown dettagliati per: strumento (`US500`, `USTEC`, `DE40`), direzione (`LONG` vs `SHORT`), giorno della settimana, orario e fascia di punteggio.
    - Generatore di scorecard formattata in testo.
  - `src/backtest/plotter.py`: Generatore di grafici per setup e trade (`TradePlotter`) salvati in `reports/`:
    - Candlestick ad alto contrasto con tema scuro/neon.
    - Range di accumulazione ombreggiato con linea di equilibrio (50%).
    - FVG e livelli OTE evidenziati con trasparenze graduate.
    - Livelli orizzontali di Entry, Stop Loss, TP1 e TP2 con indicazione del PnL e R-multiplo conseguito.
  - Test suite per il backtesting (`tests/test_backtest.py`), portando la suite complessiva a 41 test (100% passati).

# 🗺️ TR-AI — Roadmap di Sviluppo

Documento di tracciamento delle milestone di progetto.

---

## 📌 Stato Avanzamento Generale

| Fase | Descrizione | Stato | Note |
| :--- | :--- | :---: | :--- |
| **FASE 0** | Analisi requisiti, chiarimento vincoli e analisi rischi |  Completata | Identificato vincolo MT5 macOS/Windows, capitale 1000€, Indici CFD |
| **FASE 1** | Progettazione architetturale di sistema |  Completata | Creato documento architetturale completo, diagrammi e interfacce |
| **S0** | Formalizzazione Strategia WAM-FVG |  Completata | Redatto `STRATEGY_SPEC.md` e scheletro YAML |
| **S1** | Primitive WAM-FVG con Test Unitari |  Completata | Sessioni/DST, Kaufman ER Range, Sweep, MSS, FVG, Fib OTE, VWAP, Volume Profile (24 test) |
| **S2** | Macchina a Stati & Plug-in Strategy |  Completata | FSM deterministica, `WamFvgStrategy`, motore di scoring 0-100, `RiskManager` centralizzato (36 test) |
| **S3** | Backtest & Report con Dati Reali |  Completata | `BacktestEngine` ad eventi, slippage/penetrazione, conservative SL/TP conflict, parziale 50% + BE, metriche R, download dati reali YFinance (60gg 5m US500, USTEC, DE40): Win Rate 66.7%, Profit Factor 3.47, Expectancy +2.00R |
| **S4** | Web Dashboard di Monitoraggio (Glassmorphism) |  Completata | Backend FastAPI, TradingView Lightweight Charts, KPI account live, posizioni & storico, log decisionali, Kill Switch hardware/web |
| **S5** | Extended Sensitivity Backtest (Robustezza) |  Completata | Matrice comparativa SL buffer [1,2,3,5,10 tick], TP1 offset [-2,0,+2 tick], 50% partial+BE vs 100% full exit (`scripts/run_sensitivity_backtest.py`) |
| **S6** | Bot Telegram & Notifiche Push Real-Time |  Completata | Motore Telegram asincrono (`TelegramBot`), comandi `/status`, `/positions`, `/trades`, `/kill`, `/resume`, sicurezza multi-tenant e fallback mock |
| **S7** | Live Paper Trading Engine (Forward-Testing) |  Completata | Runner continuo (`LivePaperRunner` e `scripts/run_live_paper.py`) sincronizzato con orari di mercato, FastAPI e Telegram, pronto per l'apertura mercati |
| **S8** | Bridge MetaTrader 5 (Demo Reale) | ⏹️ Pianificata | Connessione broker MT5 (quando richiesto dall'utente dopo fase simulata) |

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
| **S3** | Backtest & Report con Grafici |  Completata | `BacktestEngine` ad eventi, slippage/penetrazione, conservative SL/TP conflict, parziale 50% + BE, metriche R, visualizzatore grafico `TradePlotter` (41 test) |
| **S4** | Calibrazione con Esempi Storici | ⏳ In attesa | Ingestione del CSV di calibrazione compilato dall'utente e tuning dei parametri |
| **S5** | Paper Trading + Web Dashboard + Telegram | ⏹️ Pianificata | Monitoraggio live glassmorphism e approvazione ordini via bot Telegram |
| **S6** | Robustezza & Ablation Testing | ⏹️ Pianificata | Walk-forward, sensitivity analysis dei tick buffer |

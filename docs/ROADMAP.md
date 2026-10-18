# 🗺️ TR-AI — Roadmap di Sviluppo

Documento di tracciamento delle milestone di progetto.

---

## 📌 Stato Avanzamento Generale

| Fase | Descrizione | Stato | Note |
| :--- | :--- | :---: | :--- |
| **FASE 0** | Analisi requisiti, chiarimento vincoli e analisi rischi |  Completata | Identificato vincolo MT5 macOS/Windows, capitale 1000€, Indici CFD |
| **FASE 1** | Progettazione architetturale di sistema |  Completata | Creato documento architetturale completo, diagrammi e interfacce |
| **S0** | Formalizzazione Strategia WAM-FVG |  Completata | Redatto `STRATEGY_SPEC.md` e scheletro YAML |
| **S1** | Primitive WAM-FVG con Test Unitari |  Completata | Sessioni/DST, Kaufman ER Range, Sweep, MSS, FVG, Fib OTE, VWAP, Volume Profile (24/24 test passati) |
| **S2** | Macchina a Stati & Plug-in Strategy | ⏳ In attesa | FSM deterministica a candela chiusa integrata con Risk Manager |
| **S3** | Backtest & Report con Grafici | ⏹️ Pianificata | Simulatore slippage/spread, metriche R, grafici setup |
| **S4** | Calibrazione con Esempi Storici | ⏹️ Pianificata | Benchmark contro esempi reali dell'utente (template CSV pronto) |
| **S5** | Paper Trading + Web Dashboard + Telegram | ⏹️ Pianificata | Monitoraggio live glassmorphism e approvazione ordini via bot |
| **S6** | Robustezza & Ablation Testing | ⏹️ Pianificata | Walk-forward, sensitivity analysis dei tick buffer |

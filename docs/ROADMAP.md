# 🗺️ TR-AI — Roadmap di Sviluppo

Documento di tracciamento delle milestone di progetto.

---

## 📌 Stato Avanzamento Generale

| Fase | Descrizione | Stato | Note |
| :--- | :--- | :---: | :--- |
| **FASE 0** | Analisi dei requisiti, chiarimento vincoli e analisi rischi |  Completata | Identificato vincolo MT5 macOS/Windows, capitale 1000€, Indici CFD |
| **FASE 1** | Progettazione architetturale di sistema |  In Revisione | Creato documento architetturale completo e interfacce astratte |
| **FASE 2** | Roadmap dettagliata con criteri di accettazione | ⏳ Da avviare | Definizione sprint e deliverable testabili |
| **FASE 3** | Implementazione Core & Config & Storage (SQLite) | ⏹️ Pianificata | Pydantic settings, SQLAlchemy models, EventBus |
| **FASE 4** | Data Layer & Paper Broker Engine | ⏹️ Pianificata | YFinance provider, motore simulazione lotti/spread su indici |
| **FASE 5** | Risk Management Engine | ⏹️ Pianificata | Vincolo 2% trade, 5% max drawdown, max 3 trade |
| **FASE 6** | Strategy Engine & Integrazione Strategia Utente | ⏹️ Pianificata | Multi-timeframe H1 + M15 su S&P500, NASDAQ, DAX |
| **FASE 7** | Web Dashboard Glassmorphism (FastAPI + WS) | ⏹️ Pianificata | Interfaccia moderna con TradingView Lightweight Charts |
| **FASE 8** | Telegram Bot & Controllo Remoto | ⏹️ Pianificata | Comandi /status, /killswitch e approvazione ordini |
| **FASE 9** | Data Provider News / Macro & Investing.com | ⏹️ Pianificata | Calendario economico e filtri pre-market |
| **FASE 10** | Connettore MT5 reale (VPS Windows) | ⏹️ Pianificata | Attivabile quando richiesto dall'utente |

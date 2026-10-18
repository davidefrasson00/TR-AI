# 📝 TR-AI — Changelog

Tutte le modifiche significative apportate a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Fase 0**: Analisi completa dei requisiti, identificazione vincolo macOS vs MetaTrader 5 (Windows), opzioni di mitigazione e chiarimento target operativi.
- **Fase 1**: Specifica dell'architettura di sistema modulare ad eventi (`docs/ARCHITECTURE.md`).
- Definizione dei parametri vincolanti di portafoglio: Capitale 1.000€, Indici CFD (S&P500, NASDAQ, DAX), timeframe M15-H1, Max 2% rischio/trade, Max 5% drawdown giornaliero, Max 3 posizioni contemporanee con rischio cumulativo $\le 5\%$.
- Architettura Web Dashboard a tema **Glassmorphism** basata su FastAPI, WebSockets e TradingView Lightweight Charts.
- Struttura iniziale documentale (`ROADMAP.md`, `CHANGELOG.md`).

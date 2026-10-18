# 📝 TR-AI — Changelog

Tutte le modifiche significative apportate a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Fase S2**: Completamento dell'integrazione plug-in della strategia WAM-FVG e del Risk Manager:
  - `src/core/events.py`: Modelli di dominio tipizzati (`Bar`, `Signal`, `Order`, `Position`, `AccountInfo`).
  - `src/core/logger.py`: Logger strutturato `DecisionLogger` per tracciare ogni decisione, soglia e motivazione.
  - `src/risk/manager.py`: Gateway centrale di Risk Management non bypassabile:
    - Position sizing dinamico sulla distanza dello Stop Loss ($Size = \frac{\text{Rischio Monetario}}{\text{StopDist} \times \text{PointValue}}$).
    - Limite max 1.0% rischio per trade (€10.00 su €1.000).
    - Circuit breaker al 3.0% di drawdown massimo giornaliero con arresto nuove operazioni.
    - Limite max 3 posizioni aperte contemporaneamente.
    - Bucket di correlazione `us_indices` (US500 e USTEC non possono avere 2 posizioni parallele).
    - Rifiuto categorico di ordini sprovvisti di Stop Loss o con $R:R < 2.0$.
  - `src/strategies/base.py`: Protocollo formale `BaseStrategy`.
  - `src/strategies/wam_fvg/fsm.py`: Macchina a stati finita deterministica (`IDLE`, `RANGE_BUILDING`, `RANGE_VALID`, `SWEEP_DETECTED`, `DISPLACEMENT_CONFIRMED`, `AWAIT_RETEST`, `ORDER_PENDING`, `IN_TRADE`, `MANAGED`, `CLOSED`) con stati di fallimento (`NO_RANGE`, `SWEEP_INVALID`, `SETUP_EXPIRED`, `SETUP_INVALIDATED`, `MISSED`).
  - `src/strategies/wam_fvg/scoring.py`: Motore di scoring 0-100 basato sulla rubrica a 6 componenti con soglia di qualificazione a 60/100.
  - `src/strategies/wam_fvg/strategy.py`: Plug-in `WamFvgStrategy` completo, ingestione candele incrementale a barra chiusa senza look-ahead bias, calcolo stop loss con buffer protettivo e spread ask per posizioni short.
  - Nuove suite di test: `test_risk_manager.py`, `test_fsm.py`, `test_scoring.py`, `test_strategy_integration.py` (36 test complessivi, 100% passati).

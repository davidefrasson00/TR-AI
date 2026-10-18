# 📝 TR-AI — Changelog

Tutte le modifiche significative apportate a questo progetto saranno documentate in questo file.

Il formato è basato su [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- **Fase S1**: Implementazione delle primitive quantitative per la strategia WAM-FVG in `src/strategies/wam_fvg/primitives/`:
  - `sessions.py`: Gestione orari con timezone-aware (`zoneinfo`), finestre operative e test specifico sul disallineamento dell'ora legale (DST) USA/Europa.
  - `range.py`: Validatore accumulazione con **Kaufman Efficiency Ratio (ER)** per garantire lateralità ($ER \le 0.35$), bounds di altezza su $ATR_{14}$ e concentrazione barre interne.
  - `sweep.py`: Rilevatore manipolazione (Spring / UTAD) con calcolo profondità in frazione del range ($0.03 \le \text{Depth} \le 0.50$) e filtro sulle chiusure consecutive esterne.
  - `displacement.py`: Validatore rientro impulsivo e Market Structure Shift (MSS) con ratio corpo/ATR $\ge 1.0$, chiusura nel 30% estremo e rottura dello swing pivot locale.
  - `fvg.py`: Rilevatore Fair Value Gap (a 3 candele senza look-ahead), calcolo Consequent Encroachment (CE al 50%) e tracciamento del ciclo di vita (`INTACT`, `TOUCHED`, `CE_HIT`, `FILLED`, `INVERTED`).
  - `fibonacci.py`: Livelli di ritracciamento e calcolo zona OTE (0.62 - 0.79) con intersezione geometrica di confluenza con gli FVG.
  - `indicators.py`: ATR, Anchored VWAP con bande di deviazione standard $\pm 1\sigma, \pm 2\sigma$ su tick volume e Volume Profile con POC e Value Area al 70%.
- Template CSV per esempi storici di calibrazione: `data/calibration/wam_fvg_examples_template.csv`.
- Suite completa di 24 test unitari su dati sintetici (`tests/strategies/wam_fvg/`) tutti con esito positivo (100% pass).
- File di configurazione `pytest.ini`.

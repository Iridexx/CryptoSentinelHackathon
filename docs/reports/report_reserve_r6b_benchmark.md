# Report — R6b: benchmark riserva + volatility budget

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R6b / decisioni D27, D28.

## COSA È STATO FATTO

1. **Benchmark su `GET /api/v1/agent/reserve/history`** (D27) — per ogni punto
   snapshot, se il range ha ≥ 2 punti:
   - `reserve_pct` — rendimento cumulato della riserva dal primo snapshot
     (`value / first_value − 1`);
   - `btc_hold_pct` — **riuso di `_btc_benchmark`** (`api/routes/views.py`), che
     allinea il % di BTC per offset orario e gestisce già il clock simulato;
   - `trading_pct` — serie `PnlSnapshot` nella stessa finestra, allineata per
     offset orario, % dal primo valore.
2. **Volatility budget** (D28) — `schemas/views.py::VolatilityBudgetView` +
   `persistence/views.py::_volatility_budget(snapshots)`:
   - serie giornaliera (una per data) da `PnlSnapshot.total_equity_usd` (solo
     trading) e `total_portfolio_equity_usd` (trading + riserva);
   - per ciascuna: deviazione standard dei rendimenti giornalieri e max drawdown;
   - `status = "ready"` solo con ≥ 7 rendimenti giornalieri (stessa soglia dello
     Sharpe), altrimenti `insufficient_data`;
   - campo `volatility_budget` in `GlobalView`.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_benchmark.py` — **4 test nuovi verdi**:
  `_volatility_budget` con dati insufficienti; con ~10 giorni dove il portafoglio
  è meno volatile del trading → `total_daily_vol_pct < trading_daily_vol_pct` e
  `total_max_drawdown_pct ≤ trading_max_drawdown_pct`; `GlobalView` include
  `volatility_budget` con `status ready`; `/history` espone
  `reserve_pct` (+15%), `btc_hold_pct` (mock), `trading_pct` (+6%).
- Suite backend completa: **346 passati** (+4), 1 skip, **15 falliti = identici
  sul tree pulito** (pre-esistenti). Zero regressioni.
- `import backend.app.main` OK; `ruff` pulito sui file toccati.

## SCOSTAMENTI DAL PIANO

Nessuno. Il **toggle UI "Solo Trading / Portafoglio Totale"** e la resa grafica
del benchmark restano a R7 (frontend); qui è tutto backend/dati.

## STATO DELIVERABLE

- `schemas/views.py`, `persistence/views.py`, `api/routes/reserve.py` — modificati.
- `tests/unit/test_reserve_benchmark.py` — creato (4 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R7** (frontend: pulsante "Bank", `BankPane`, Setup › Bank, GlobalPane).

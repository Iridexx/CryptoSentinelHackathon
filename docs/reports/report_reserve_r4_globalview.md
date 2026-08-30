# Report — R4: riserva in GlobalView e risk manager

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R4.

## COSA È STATO FATTO

1. `schemas/views.py::GlobalView` — 9 campi nuovi (tutti con default, nessuna
   rottura per i chiamanti esistenti): `reserve_value_usd`, `reserve_cash_usd`,
   `reserve_cost_basis_usd`, `reserve_pnl_usd`, `reserve_pnl_pct`,
   `reserve_fees_usd`, `tradable_equity_usd`, `total_portfolio_equity_usd`,
   `total_portfolio_pnl_pct`.
2. `persistence/views.py::ViewService`:
   - `_reserve_state(user_id)` — legge `reserve_cash_usd` /
     `reserve_transferred_net_usd` da `portfolio_state`, `sum_fees` e il valore
     dall'**ultimo `ReserveSnapshot`** (scritto ogni ora dallo slow tick in R6);
     prima del primo snapshot valuta gli asset **al costo** (P&L riserva = 0
     invece di oscillare su un prezzo stale).
   - `global_view` (entrambi i rami, con e senza `PortfolioState`):
     `tradable_equity = total_equity − reserve_cost_basis` (D25),
     `total_portfolio_equity = tradable_equity + reserve_value`,
     `total_portfolio_pnl_pct` combinato su `initial_equity`.
   - Il **P&L di trading** (`pnl_total_pct`) resta sul solo book (D2 — il guard
     non vede la riserva).
   - Fee riserva **sommate** a `total_fees_usd` (D30).
   - `_risk_guardrail` riceve `tradable_equity` per il floor `$5` (§7/D25).
3. `agent/risk/manager.py::RiskManager.evaluate` — `reserve_offset =
   portfolio.reserve_transferred_net_usd`; il floor guard e il sizing lavorano su
   `equity − reserve_offset`. Utenti senza riserva → contatore 0, comportamento
   invariato.

## SCOSTAMENTI DAL PIANO

Nessuno. `sweep_min_tradable_equity_usd` era già stato rimosso in R3.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_globalview.py` — **8 test nuovi verdi**:
  carve-out del `tradable_equity`, valore da snapshot vs fallback al costo, D25
  (BTC pompa → snapshot alto → `tradable` invariato, `pnl` trading invariato,
  `total_portfolio_equity` su), fee riserva in `total_fees_usd`, floor guardrail
  su `tradable_equity`; risk manager sizing su tradable, floor su tradable,
  invariato senza riserva.
- Suite backend completa: **323 passati** (+8), 1 skip, **15 falliti = identici
  sul tree pulito** (pre-esistenti). Zero regressioni; i test risk-engine di
  `test_agent_step6` restano verdi.
- `ruff` pulito.

## QUESTIONI APERTE

- R4b: `persistence/archive.py` deve includere le tabelle riserva e azzerare i
  campi `portfolio_state` al reset analytics.
- R6: lo slow tick deve chiamare `ReserveService.snapshot` regolarmente perché
  `_reserve_state` abbia un valore MTM fresco (fino ad allora usa il costo).

## STATO DELIVERABLE

- `schemas/views.py`, `persistence/views.py`, `agent/risk/manager.py` — modificati.
- `tests/unit/test_reserve_globalview.py` — creato (8 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R4b** su approvazione.

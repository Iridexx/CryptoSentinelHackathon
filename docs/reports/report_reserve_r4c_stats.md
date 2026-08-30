# Report — R4c: impatto delle uscite verso la riserva sulle statistiche (D31)

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R4c / decisione D31.

## ANALISI (perché questo step esiste)

Domanda: *"le uscite dall'equity come vengono gestite dalle statistiche?"*

Verifica nel codice (`agent/service.py::_update_portfolio_state`,
`api/routes/views.py::equity_curve`): tutte le statistiche (curva equity,
drawdown, Sharpe, P&L, win-rate, `daily_loss_limit`) sono calcolate su
`initial_equity + realized_trading + unrealized_trading`. Un transfer verso la
riserva **non tocca** nessuno di questi tre valori, e **non** crea un
`EquityAdjustment` → **non viene contato come perdita**. Il progetto gestisce già
il caso analogo (prelievi reali) con `EquityAdjustment`; il transfer interno è più
semplice perché non muove `initial_equity`.

Tre lacune trovate → fix in questo step (a, b) e piano per la terza (toggle in
R6b/R7).

## COSA È STATO FATTO

1. **`_update_portfolio_state`** — `exposure_pct` e `daily_loss_limit_used_pct` ora
   si calcolano su `tradable_equity = total_equity − reserve_transferred_net_usd`
   (come il risk manager, D25). Prima dividevano per l'equity trading totale
   (che include il profitto già spostato) → esposizione sottostimata e guardia
   daily-loss che scattava un po' tardi. Utenti senza riserva → offset 0,
   invariato.
2. **`PnlSnapshot.total_portfolio_equity_usd`** — colonna nuova (nullable) +
   ALTER idempotente in `_apply_column_migrations`. Rappresenta trading + riserva.
3. **`_snapshot_portfolio_hourly`** — popola la colonna: `tradable + valore
   riserva`. Fino a R6 (che scriverà `ReserveSnapshot` con MTM reale) la riserva
   è valutata **al costo**, quindi = `total_equity_usd` finché non c'è P&L riserva.
4. **`/equity-curve`** — per ogni punto `global` con la colonna valorizzata,
   espone `portfolio_equity_usd`, `portfolio_pnl_usd`, `portfolio_pnl_pct` (usano
   lo stesso `contributed` che già compensa i versamenti `EquityAdjustment`). Il
   toggle UI "Solo Trading / Portafoglio Totale" arriva in R7.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_r4c_stats.py` — **3 test nuovi verdi**:
  esposizione/daily-loss su tradable (28.57% vs 22.22%; −14.29% vs −11.11%),
  invariato senza riserva, snapshot orario con `total_portfolio_equity_usd`.
- Suite backend completa: **326 passati** (+3), 1 skip, **15 falliti = identici
  sul tree pulito** (pre-esistenti). Zero regressioni.
- `ruff` pulito su tutti i file nuovi/modificati (le 12 segnalazioni residue in
  `service.py` sono debito di lint pre-esistente, regione trailing-stop, non
  toccata da questo step — verificato con `git stash`).

## SCOSTAMENTI DAL PIANO

Nessuno.

## QUESTIONI APERTE

- Il toggle "Solo Trading / Portafoglio Totale" + peak/drawdown a livello
  portafoglio: serie backend in R6b, UI in R7.
- R6 deve scrivere `ReserveSnapshot` ogni ora perché `total_portfolio_equity_usd`
  rifletta il MTM reale della riserva (fino ad allora = costo).

## STATO DELIVERABLE

- `agent/service.py`, `api/routes/views.py`, `persistence/database.py`,
  `persistence/models/pnl.py` — modificati.
- `tests/unit/test_reserve_r4c_stats.py` — creato (3 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R4b** su approvazione.

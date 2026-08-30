# Report — R2: modelli ORM e repository della riserva "Bank"

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R2.

## COSA È STATO FATTO

Layer dati della riserva, senza logica di business (quella è R3):

1. `backend/app/persistence/models/reserve.py` — 3 modelli ORM:
   - `ReserveHolding` — posizione per asset (unique `user_id`+`asset`): `quantity`
     `Numeric(38,18)`, `avg_cost_usd`, `venue`.
   - `ReserveTransaction` — audit trail: `type` (`transfer_in`|`transfer_out`|
     `sweep`|`deploy_buy`|`rebalance_buy`|`rebalance_sell`), `asset`, `quantity`,
     `price_usd`, `value_usd`, `fee_usd`, `cash_usd_delta`, `venue`, `ref`, `note`.
   - `ReserveSnapshot` — valore orario per il grafico/benchmark: `total_value_usd`,
     `cash_usd`, `cost_basis_usd`, `pnl_usd`, `fees_cumulative_usd`, `holdings_json`.
2. `PortfolioState` (in `models/pnl.py`) — 5 colonne nuove per la contabilità
   (D25/D29/D30): `reserve_cash_usd`, `reserve_transferred_net_usd`,
   `last_swept_realized_pnl_usd`, `last_deploy_at`, `reserve_frozen`.
3. `persistence/database.py::_apply_column_migrations` — ALTER idempotenti per le
   5 colonne su DB esistenti (stesso pattern delle altre migrazioni colonna).
4. Registrazione in `models/__init__.py` e `repositories/__init__.py`.
5. `backend/app/persistence/repositories/reserve.py` — `ReserveRepository`:
   - holdings: `list_holdings`, `get_holding`, `upsert_holding`;
   - transazioni: `add_transaction`, `list_transactions` (newest-first),
     `sum_fees(user_id, since=None)` (D30);
   - snapshot: `save_snapshot` (commit), `recent_snapshots`, `snapshots_since`;
   - contatori: `get_reserve_fields` (zeri se `PortfolioState` manca),
     `set_reserve_fields` (whitelist campi, richiede la riga già seedata),
     `commit`.
   - I mutatori (`upsert_holding`, `add_transaction`, `set_reserve_fields`) fanno
     **flush, non commit**: il servizio R3 possiede la transazione e committa una
     volta sola → transfer/deploy atomici.

## COME È STATO FATTO

- Precisione: quantità `Numeric(38,18)`, USD `Numeric(20,8)`, prezzi `Numeric(30,18)`
  come il resto del layer.
- I contatori riserva stanno su `PortfolioState` (colonne vere, pattern
  `_apply_column_migrations`) e non in `extra_json`: sono letti/scritti spesso e
  vanno interrogati.
- Nessuna modifica a `ViewService`, risk manager, scheduler, API o frontend.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_persistence.py` — **11 test nuovi verdi**:
  creazione tabelle, colonne su `portfolio_state`, upsert holding create/update,
  ordinamento, transazioni newest-first, `sum_fees` (totale e `since`), snapshot
  save/recent/since, `get_reserve_fields` a vuoto, `set_reserve_fields` senza riga
  → `ValueError`, update+readback, campo sconosciuto → `ValueError`, rollback
  scarta i mutatori flush-only.
- `pytest test_reserve_persistence + test_reserve_config + test_persistence_layer`
  → 48 passati.
- Suite backend completa: 299 passati, 1 skip, **15 falliti = identici sul tree
  pulito** (verificato con `git stash`): tz-naive/aware datetime, venue registry
  mancante, `ANTHROPIC_API_KEY` assente. **Zero regressioni da R2.**
- `import backend.app.main` OK. `ruff check` pulito.

## SCOSTAMENTI DAL PIANO

Nessuno. Il piano prevedeva "`extra_json` o colonne `upgrade_schema`": scelte le
colonne, coerente con la house style.

## QUESTIONI APERTE

- R3: `ReserveService` (transfer_in/out, sweep, deploy §8ter, rebalance, valuate,
  snapshot, set_frozen) + `ReserveExecutor` (dry-run) + fallback `initial_equity`
  + atomicità (single commit sui mutatori del repo).

## STATO DELIVERABLE

- `models/reserve.py`, `repositories/reserve.py` — creati.
- `models/pnl.py`, `database.py`, `models/__init__.py`, `repositories/__init__.py`
  — modificati.
- `tests/unit/test_reserve_persistence.py` — creato (11 test).
- Doc: `PROJECT_STRUCTURE.md` aggiornato.
- Prossimo step: **R3** su approvazione.

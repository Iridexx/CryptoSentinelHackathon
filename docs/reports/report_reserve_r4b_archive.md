# Report — R4b: reset/archivio della riserva "Bank"

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R4b / decisione D20.

## COSA È STATO FATTO

`backend/app/persistence/archive.py` — le due funzioni di reset ora trattano
anche la riserva:

1. **`archive_dry_run_records`** (reset simulato):
   - `reserve_holdings`, `reserve_transactions`, `reserve_snapshots` vengono
     copiati nel payload di `ArchivedRun`;
   - quando `delete_live=True` vengono cancellati **tutti** (la riserva è
     interamente simulata in questa fase);
   - `_clear_reserve_counters(portfolio, ...)` azzera i campi riserva su
     `PortfolioState` (`reserve_cash_usd`, `reserve_transferred_net_usd`,
     `last_swept_realized_pnl_usd`, `last_deploy_at`, `reserve_frozen`) — **sempre
     quando si cancellano le righe**, non solo se c'è un reset del capitale:
     lasciare `reserve_transferred_net_usd` che punta a una riserva ormai vuota
     corromperebbe `tradable_equity`.
2. **`reset_all_data`** (wipe totale):
   - stesse tre tabelle nel payload di backup (se `backup_label`), nei `counts` e
     nella cancellazione;
   - il `PortfolioState` ricreato ha i campi riserva ai default di colonna
     (0 / False / NULL), quindi nessun intervento extra.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_archive.py` — **4 test nuovi verdi**:
  archivio+cancellazione+azzeramento contatori; azzeramento anche senza reset del
  capitale; `reset_all_data` con backup (payload + counts); `reset_all_data`
  senza backup che cancella comunque la riserva.
- `pytest test_reserve_archive + test_persistence_layer` → 30 passati (i test
  archive esistenti non rotti: verificano chiavi specifiche in `deleted`).
- Suite backend completa: **330 passati** (+4), 1 skip, 15 falliti pre-esistenti.
  Zero regressioni.
- `ruff` pulito.

## SCOSTAMENTI DAL PIANO

Nessuno.

## STATO DELIVERABLE

- `persistence/archive.py` — modificato.
- `tests/unit/test_reserve_archive.py` — creato (4 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R5** (API `/agent/reserve/*` + router + i18n).

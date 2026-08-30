# Report — R5: API della riserva "Bank"

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R5.

## COSA È STATO FATTO

1. `backend/app/domain/reserve/pricing.py`:
   - `fetch_reserve_prices(settings)` — prezzo USD dei 5 asset in **una** chiamata
     batch al ticker **spot** di Binance (`/api/v3/ticker/price`); degrada a
     "nessun prezzo" se la rete non risponde.
   - `build_reserve_service(session, settings)` — factory: pre-carica i prezzi,
     costruisce `ReserveExecutor` con un price source a dizionario (zero chiamate
     per-asset), restituisce `ReserveService`. Riusata da route e slow tick (R6).
2. `backend/app/api/routes/reserve.py` — router `/api/v1/agent/reserve`:
   | metodo | path | auth | |
   |---|---|---|---|
   | GET | `` | read | `ReserveView` |
   | GET | `/history?range=24h\|7d\|all` | read | serie `ReserveSnapshot` |
   | GET | `/settings` | read | `ReserveSettingsResponse` (default/persisted) |
   | POST | `/settings` | admin | salva override; se `enabled=false` con asset dentro → **freeze** (D22) |
   | POST | `/transfer` | admin | `{amount_usd, direction: in\|out}` |
   | POST | `/target-weights` | admin | `{weights: {...}}` (rivalidato: somma 100) |
   | POST | `/rebalance` | admin | `{dry_run?}` |
   | POST | `/deploy` | admin | "Deploy ora" (`force=True`) |
   - `ReserveError` → HTTP 400 con `detail = <code>` (es. `no_profit_available`,
     `cooldown`, `drawdown_guard`, `frozen`); prezzi non disponibili → 503
     `price_unavailable`.
3. Router registrato in `api/routes/__init__.py`.
4. Chiavi i18n `reserve.*` in `locales/en.json` e `it.json` (nome scheda + messaggi
   d'errore). Base EN.
5. Fix `ReserveService.set_target_weights` — rivalida via `ReserveSettings.model_validate`
   (prima passava dict grezzi a `reconcile_with_config`).

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_api.py` — **7 test nuovi verdi**
  (`TestClient` + override sessione/auth + `fetch_reserve_prices` monkeypatchato):
  GET reserve vuota (5 holdings), transfer_in senza profitto → 400, transfer_in
  con profitto → riserva finanziata (BTC/ETH/BNB comprati), roundtrip settings
  (default→persisted, sweep_pct 20→35), `enabled=false` con holdings → `frozen`,
  validazione target-weights (200 / 400), deploy + rebalance dry-run + history.
- `import backend.app.main` OK.
- Suite backend completa: **337 passati** (+7), 1 skip, **15 falliti = identici
  sul tree pulito** (pre-esistenti). Zero regressioni.
- `ruff` pulito; JSON i18n validi (`utf-8-sig`).

## SCOSTAMENTI DAL PIANO

Nessuno. Il benchmark su `/history` (`reserve_pct`/`btc_hold_pct`/`trading_pct`)
resta a R6b come previsto — per ora `/history` ritorna la serie grezza.

## STATO DELIVERABLE

- `api/routes/reserve.py`, `domain/reserve/pricing.py` — creati.
- `api/routes/__init__.py`, `domain/reserve/service.py`, `locales/{en,it}.json` — modificati.
- `tests/unit/test_reserve_api.py` — creato (7 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R6** (slow tick: valuate + snapshot + sweep + deploy + rebalance + notifiche).

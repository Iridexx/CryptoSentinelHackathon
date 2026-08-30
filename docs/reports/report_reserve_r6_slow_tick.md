# Report — R6: la riserva "Bank" nel loop dell'agente

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R6.

## COSA È STATO FATTO

1. `AgentService._reserve_tick(session, now)` — nuovo passo nel `slow_tick`
   (prima di `_snapshot_portfolio_hourly`):
   - **no-op** se `settings.reserve.enabled` è false;
   - costruisce il servizio con `build_reserve_service` (prezzi Binance spot batch);
   - **sweep** → **deploy** → **rebalance** (solo se `auto_rebalance`) — ogni
     chiamata è una transazione a sé e si auto-salta se il proprio guard lo dice
     (disabilitato / congelato / drawdown guard / nessun trigger);
   - `hard_stop` salta sweep/deploy/rebalance **ma esegue comunque lo snapshot**;
   - **`ReserveSnapshot` orario** (MTM reale) con dedup su
     `snapshot_interval_minutes` (default 60);
   - ogni eccezione è loggata e non blocca il tick.
2. `_snapshot_portfolio_hourly` — `total_portfolio_equity_usd` ora usa il valore
   dell'**ultimo `ReserveSnapshot`** (MTM reale scritto da `_reserve_tick`), con
   fallback al costo prima del primo snapshot.
3. `AgentNotifier.notify_reserve_event(user_id, kind, detail)` — push per
   `sweep` / `deploy` / `rebalance` / `transfer` (D23); opt-out via il nuovo
   toggle `NotificationPreferences.reserve_events` (default ON, incluso nel
   round-trip GET/PUT `/api/v1/notifications/preferences`).
4. `POST /api/v1/agent/reserve/transfer` — invia una `notify_reserve_event`
   `transfer` a operazione riuscita (non blocca mai il transfer).

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_slow_tick.py` — **5 test nuovi verdi**:
  tick che fa sweep+deploy+snapshot (profitto $200 → riserva $40 → BTC/ETH/BNB),
  no-op se disabilitato, `hard_stop` che salta le azioni ma snapshotta, dedup
  dello snapshot per intervallo (1 → 1 dopo 10 min → 2 dopo 70 min),
  `_snapshot_portfolio_hourly` che usa il MTM della riserva.
- `test_reserve_slow_tick + test_reserve_api + test_reserve_service +
  test_persistence_layer` → 54 passati.
- Suite backend completa: **342 passati** (+5), 1 skip, **15 falliti = identici
  sul tree pulito** (pre-esistenti; i test risk-engine e daily-summary restano
  verdi). Zero regressioni.
- `import backend.app.main` OK; `ruff` pulito sui file nuovi/modificati (le 12
  segnalazioni residue in `service.py` sono nella regione trailing-stop
  pre-esistente, fuori da questo step).

## SCOSTAMENTI DAL PIANO

Nessuno. Il benchmark `reserve_pct`/`btc_hold_pct`/`trading_pct` su `/history` e
il volatility budget restano a R6b.

## STATO DELIVERABLE

- `agent/service.py` — `_reserve_tick` + `_snapshot_portfolio_hourly` MTM.
- `notifications/agent_notifier.py`, `schemas/notification_prefs.py`,
  `api/routes/reserve.py` — modificati.
- `tests/unit/test_reserve_slow_tick.py` — creato (5 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R6b** (benchmark riserva + volatility budget).

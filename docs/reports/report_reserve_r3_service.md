# Report — R3: ReserveService + ReserveExecutor

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R3.

## COSA È STATO FATTO

La logica di business della riserva "Bank", **solo fase simulata**.

1. `backend/app/domain/reserve/executor.py` — `ReserveExecutor`:
   - `buy(asset, usd)` / `sell(asset, qty)` — simulato: prezzo dal `price_source`
     iniettato, fee = `compute_spot_costs(..., "all")` (swap 0.05% + slippage 0.10%)
     + `SIM_GAS_USD` ($0.15 flat, il costo fisso che giustifica `deploy_min_buy_usd`).
   - Ramo `live` → `NotImplementedError` (fino a R10).
   - `price_source` iniettabile → in R6 sarà il feed Binance klines.
2. `backend/app/domain/reserve/service.py` — `ReserveService`:
   - `transfer_in` — cap `min(richiesto, max(0, tradable − initial))` (§7bis/D21);
     blocco se `frozen`; accredita `reserve_cash_usd` + contatore, poi `deploy()`.
   - `run_profit_sweep` — §8bis: `sweep_pct` dell'incremento di P&L realizzato
     sopra l'high-water mark; cap §7bis; solo cash, nessun acquisto; HWM avanzato
     solo per il profitto effettivamente consumato; skip se disabilitato / guard /
     frozen.
   - `deploy` — §8ter: trigger 7 giorni **o** cash ≥ soglia (o `force`); ordina
     per **gap relativo**; riempimento **greedy** (ogni asset fino al suo gap dal
     cash residuo, mai < `deploy_min_buy_usd`); anti-starvation sul top asset se
     nessuno qualifica e trigger a tempo; resto → cash. Importi arrotondati ai
     centesimi (`ROUND_DOWN`) per evitare rumore sub-cent.
   - `transfer_out` — cooldown + blocco durante il guard drawdown; svuota prima il
     cash, poi vende asset **pro-rata**; il contatore `reserve_transferred_net_usd`
     cala del **netto accreditato** al trading (D25), la fee resta drag sul
     `reserve_pnl`.
   - `rebalance` — vende il sovrappeso oltre `rebalance_band_pct`, proventi → cash
     → `deploy(force=True)`. (In R6 resterà manuale.)
   - `set_target_weights`, `set_frozen`, `valuate`, `snapshot`, `get_view`.
   - **`initial_equity` fallback** = `Settings.dry_run_capital_usd` se manca
     `PortfolioState`.
   - **Atomicità**: ogni transfer/sweep/deploy/rebalance = un `commit` unico
     (holdings + `reserve_transactions` + contatori); i mutatori del repo fanno
     `flush`, il servizio committa.
3. Config: `ReserveConfig`/`ReserveSettings`/`reserve.yaml` — rimosso
   `sweep_min_tradable_equity_usd` (superato da §7bis), aggiunti
   `rebalance_band_pct` (12), `deploy_interval_days` (7), `deploy_min_cash_usd` (40),
   `deploy_min_buy_usd` (5).
4. Schemi `ReserveView` / `ReserveHoldingView` in `schemas/reserve.py`.

## SCOSTAMENTI DAL PIANO

- L'allocazione del deploy (§8ter step 5) è **greedy per priorità**, non
  proporzionale: la versione proporzionale diluiva le fette sotto `deploy_min_buy_usd`
  quando un asset aveva un gap minuscolo, affamando i tail 5%. Piano §8ter step 5
  aggiornato.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_service.py` — **16 test nuovi verdi**:
  §7bis (rifiuto senza profitto, cap al profitto, blocco frozen), sweep (quota,
  idempotenza, disabilitato), deploy ($40 vuota → BTC/ETH/BNB, SOL/TRX rimandati
  con ~$4 cash; priorità ai tail quando i big three sono a target; skip senza
  trigger), transfer_out (svuota cash poi vende, contatore al netto; cooldown;
  blocco guard), D25 (prezzo raddoppia → `tradable` invariato, `pnl` su),
  D30 (fee tracciate, drag sul pnl), atomicità (leg fallita → rollback totale),
  frozen blocca deploy/sweep.
- `test_reserve_service + test_reserve_config + test_reserve_persistence` → 38 passati.
- Suite backend completa: **315 passati** (+16), 1 skip, **15 falliti = identici
  sul tree pulito** (pre-esistenti). Zero regressioni.
- `import backend.app.main` OK, `ruff` pulito.

## QUESTIONI APERTE

- R4: `GlobalView` (D25 — `tradable_equity` + P&L combinato), risk manager su
  `tradable_equity`, fee riserva in `total_fees_usd`.
- R4b: reset/archivio.

## STATO DELIVERABLE

- `domain/reserve/executor.py`, `service.py` — creati.
- `domain/reserve/__init__.py`, `schemas/reserve.py`, `core/config.py`,
  `configs/reserve.yaml` — modificati.
- `tests/unit/test_reserve_service.py` — creato (16 test).
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Prossimo step: **R4** su approvazione.

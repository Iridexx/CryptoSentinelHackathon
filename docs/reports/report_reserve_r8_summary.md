# Report — R8: chiusura scheda "Bank" / Riserva di Valore

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R8 (chiusura backend + frontend simulato).

## COSA È STATA LA FEATURE

Un **sotto-portafoglio di tesoreria** dentro l'app dell'agente: l'utente sposta
i **soli profitti** in 5 hard asset (BTC/ETH/BNB/SOL/TRX, wrapped/Binance-Peg),
per fare da zavorra stabile al book di trading e ridurre nel tempo la volatilità
del portafoglio. 31 decisioni (D1–D31), 13 step (R1–R10; R9/R10 futuri).

### Regole cardine
- **§7bis / D21 — solo profitti**: ogni `transfer_in` (manuale e sweep) è capato a
  `max(0, tradable_equity − initial_equity)`. Il capitale iniziale non entra mai.
- **D25 — contabilità**: `tradable_equity = total_equity − reserve_transferred_net_usd`
  (contatore, non valore di mercato) → il sizing del risk manager non si muove
  quando il mercato muove la riserva.
- **D2 — guard drawdown**: la riserva è esclusa dal blocco -15% del trading, ma
  compare nel P&L/equity totali.
- **D29 — sweep vs deploy**: sweep ogni 24h (sposta il 20% del nuovo profitto in
  un saldo USDC, zero fee); deploy in batch ogni 7 giorni o a $40 di cash, greedy
  per gap relativo, mai un acquisto < $5 (i tail 5% aspettano 1–2 cicli).
- **D30 — fee**: ogni movimento con costo registra `fee_usd`; totale in
  `reserve_fees_usd` e nel `total_fees_usd` del portafoglio; drag sul P&L riserva.
- **D31 — statistiche**: i transfer NON contano come perdite; `exposure_pct` e
  `daily_loss_limit_used_pct` su `tradable_equity`; serie `total_portfolio_equity_usd`.

## COSA È STATO CONSEGNATO (R1–R7b)

| step | contenuto |
|---|---|
| R1, R1b | `configs/reserve.yaml`, `ReserveConfig`/`ReserveSettings`, diagnostica Aster spot (TRX assente → venue = PancakeSwap) |
| R2 | ORM `ReserveHolding`/`ReserveTransaction`/`ReserveSnapshot` + 5 colonne `PortfolioState` + repository |
| R3 | `ReserveService` (transfer/sweep/deploy/rebalance/valuate/snapshot) + `ReserveExecutor` simulato (`live` = NotImplementedError) |
| R4, R4c, R4b | `GlobalView` D25, risk manager su tradable, esposizione/daily-loss su tradable, `total_portfolio_equity_usd`, reset/archivio |
| R5 | API `/api/v1/agent/reserve/*` (8 route) + i18n |
| R6, R6b | slow tick `_reserve_tick` + `AgentNotifier.notify_reserve_event`; benchmark + volatility budget |
| R7a, R7b | pulsante 🏦 + `BankPane`, Setup › Bank, GlobalPane card + volatility budget, toggle equity "Solo trading / Portafoglio totale", `agentApi.ts` |

## COSA È STATO VERIFICATO (R8)

Interprete: `backend\.venv\Scripts\python.exe`.

- **Startup**: `import backend.app.main` OK; `Settings(**load_yaml_settings())`
  costruisce; 8 route reserve registrate in `api_router`.
- **Guardrail hard invariati**: 148 eligible token (`eligible_tokens.yaml` NON
  toccato), somma pesi riserva = 100 ±0.01.
- **Test riserva dedicati**: `test_reserve_{config,persistence,service,globalview,
  r4c_stats,archive,api,slow_tick,benchmark}.py` → **70 passati**.
- **Suite backend completa** (ultimo run R7b): **347 passati**, 1 skip, 15 falliti
  **pre-esistenti e identici sul tree pulito** (tz datetime in trailing/golden/
  support — non collegati alla riserva). Zero regressioni introdotte in R1–R8.
- `ruff` pulito su tutti i moduli riserva; `tsc --noEmit` exit 0; `eslint`
  `AgentTab.tsx` invariato (6 errori di debito React pre-esistente, zero nuovi).

## QUESTIONI APERTE / FUORI SCOPE

- **R9** — mirror della scheda sulla dashboard web (`dashboard/src/App.tsx`).
- **R10** — esecuzione **live** su PancakeSwap: `ReserveExecutor.live` è uno stub;
  serve verificare gli indirizzi BEP20 on-chain, sbloccare il gate testnet e
  misurare la liquidità Binance-Peg di SOL/TRX.
- `reserve_events` (notifiche) è cablato lato backend (default ON) ma manca una
  UI delle preferenze notifiche nell'app — task indipendente.
- Verifica visiva del frontend non eseguita (il build caricherebbe `.env` reale).

## STATO DELIVERABLE

Feature **completa in modalità simulata** e integrata (config → dominio → viste →
API → automazioni → frontend). Piano, `PROJECT_STRUCTURE.md` e 12 report per step
aggiornati. Commit R1→R8 sul branch `main`, non pushati.

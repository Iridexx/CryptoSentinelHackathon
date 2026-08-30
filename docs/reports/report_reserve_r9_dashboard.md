# Report — R9: mirror scheda "Bank" sulla dashboard web

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R9.

## COSA È STATO FATTO

Solo `dashboard/` (progetto Vite separato, nessuna modifica backend).

1. `dashboard/src/types.ts`:
   - `GlobalView` esteso con i campi riserva (D25) e `volatility_budget` (D28);
   - `NotificationPreferences` + `reserve_events`;
   - `EquityCurvePoint` non toccato qui (il grafico dashboard resta sul trading);
   - nuovi tipi `ReserveView`, `ReserveHoldingView`, `ReserveSettings`,
     `ReserveSettingsResponse`, `ReserveTargetWeight`, `ReserveTransactionRow`;
   - completati `SpotView`/`PerpView` con `volume_total_usd?`/`volume_today_usd?`
     (campi già usati in App.tsx dal commit dashboard precedente ma mancanti nei
     tipi → 4 errori tsc pre-esistenti risolti).
2. `dashboard/src/api.ts` — `fetchReserve`, `fetchReserveTransactions`,
   `fetchReserveSettings`, `saveReserveSettings`, `reserveTransfer`,
   `reserveDeploy`, `reserveRebalance`.
3. `dashboard/src/App.tsx`:
   - tab **Bank** (`Tab` + `tabs`) + `BankPanel` (componente autonomo, refresh 30s):
     metriche (valore, P&L, USDC, fee, capacità §7bis, % portafoglio, stato,
     prossimo deploy); tabella posizioni con peso vs target e marker "•" fuori
     banda; tabella movimenti; azioni admin (transfer in/out, deploy, rebalance)
     con mapping code→messaggio IT; form impostazioni (toggle, sweep/deploy/
     cooldown, pesi con check somma 100, salva);
   - `GlobalPanel` — metriche "Bank / Riserva", "Equity tradabile", "Portafoglio
     totale", "PnL % totale", + blocco volatility budget (max drawdown e vol
     giornaliera, trading vs con riserva) quando `status === "ready"`;
   - `NotificationPrefsPanel` / `NOTIF_PREF_LABELS` — toggle
     "Bank / Reserve Events" (`toggleNotifPref` è già spread-based → il round-trip
     funziona).

## COSA È STATO VERIFICATO

- `npx tsc --noEmit -p dashboard/tsconfig.json` → **exit 0** (nessun errore; i 4
  errori `volume_*` pre-esistenti risolti).
- `npx tsc --noEmit -p tsconfig.app.json` (mobile) → exit 0, invariato.
- `npx eslint dashboard/src/App.tsx` → **6 errori** vs **5 sul tree pulito**:
  l'errore aggiuntivo è `react-hooks/set-state-in-effect` nel `BankPanel` (fetch
  su mount + poll), **stessa categoria** dei 5 già presenti e dell'equivalente
  mobile; `npm run lint` non è CI gate (AGENTS.md — debito React da chiudere a
  parte).
- Nessuna modifica backend → suite backend non ri-eseguita (invariata a 347
  passed dal run R7b).
- Verifica visiva non eseguita (build dashboard).

## SCOSTAMENTI DAL PIANO

Nessuno. Il grafico multi-linea benchmark (`/agent/reserve/history`) non è
mostrato sulla dashboard in questo giro — il `BankPanel` è tabellare come il resto
della dashboard giudici; si può aggiungere un `EquityChart`-style in un secondo
momento.

## STATO DELIVERABLE

- `dashboard/src/{App.tsx,api.ts,types.ts}` — modificati.
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- Rimane solo **R10** (esecuzione live PancakeSwap — futuro).

# Report — R7a: frontend scheda "Bank" (pulsante + BankPane)

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R7a.

## COSA È STATO FATTO

1. `src/services/agentApi.ts`:
   - tipi `ReserveView`, `ReserveHoldingView`, `ReserveSettings`,
     `ReserveSettingsResponse`, `ReserveHistoryPoint/Response`,
     `ReserveTransactionRow/Response`, `ReserveRebalanceResponse`;
   - client: `fetchReserve`, `fetchReserveHistory`, `fetchReserveSettings`,
     `fetchReserveTransactions`, `saveReserveSettings`, `reserveTransfer`,
     `reserveSetTargetWeights`, `reserveRebalance`, `reserveDeploy`;
   - `GlobalView` esteso con i campi riserva (D25) e `volatility_budget` (D28);
   - `EquityCurveResponse.items` con `portfolio_equity_usd` / `portfolio_pnl_*`.
2. `backend/app/api/routes/reserve.py` — `GET /agent/reserve/transactions`
   (mancava; serve alla lista Movimenti).
3. `src/components/AgentTab.tsx`:
   - `AgentPane` + `'bank'`; pulsante **"🏦 Bank · Riserva di Valore"** a tutta
     larghezza sotto le due righe di pulsanti (D10);
   - `BankPane` (componente autonomo, fetch proprio + refresh 30s):
     - header: valore, P&L $/%, % del portafoglio, USDC da investire, fee pagate,
       "disponibile da spostare" (§7bis), prossimo deploy, badge "congelata";
     - stato vuoto dedicato;
     - grafico SVG multi-linea con toggle **% rendimento ↔ $ valore** e range
       24h/7g/Tutto (riserva oro, BTC blu, trading grigio);
     - pesi correnti vs target con marker "fuori banda";
     - posizioni (asset, qty, costo, valore, P&L);
     - movimenti (ultimi 8);
     - azioni admin: importo + "Sposta nella riserva" (disabilitato se capacità 0
       o congelata), "Preleva" (disabilitato in cooldown), "Deploy ora",
       "Ribilancia"; mapping code→messaggio IT per gli errori.

## COSA È STATO VERIFICATO

- `npx tsc --noEmit -p tsconfig.app.json` → exit 0 (nessun errore di tipo).
- `npx eslint src/components/AgentTab.tsx` → **6 errori, identici al tree pulito**
  (debito React pre-esistente, `npm run lint` non è ancora CI gate per AGENTS.md).
  Zero nuovi errori introdotti da `BankPane` / `agentApi.ts`.
- `import backend.app.main` OK; `pytest -k "reserve or persistence or views"` →
  100 passati; `ruff` pulito su `reserve.py`.
- Verifica visiva non eseguita (il build frontend caricherebbe `.env` reale —
  vietato da AGENTS.md; il layout segue il mockup `bank-mockup.html`).

## SCOSTAMENTI DAL PIANO

R7 spezzato in **R7a** (pulsante + BankPane + client) e **R7b** (Setup › Bank,
GlobalPane, toggle equity, `SettingsTab`).

## STATO DELIVERABLE

- `src/services/agentApi.ts`, `src/components/AgentTab.tsx`,
  `backend/app/api/routes/reserve.py` — modificati.
- Doc: plan aggiornato.
- Prossimo: **R7b**.

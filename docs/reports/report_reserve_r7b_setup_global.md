# Report — R7b: Setup › Bank + GlobalPane + toggle equity

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R7b (chiude R7).

## COSA È STATO FATTO

`src/components/AgentTab.tsx`:

1. **`BankSettingsPane`** — nuova sotto-scheda **Setup › Bank** (`SetupTab` +
   `'bank'`, tab bar `grid-cols-5`). Componente autonomo: `fetchReserveSettings`
   al mount, editing locale con dirty-flag, `saveReserveSettings` (admin):
   - toggle Riserva attiva / Ribilanciamento automatico / Sweep profitti;
   - pesi target per i 5 asset con indicatore "somma = 100%" (salvataggio
     bloccato se ≠ 100 ±0.5);
   - Sweep %, Sweep ogni (ore), Deploy ogni (giorni), Deploy se cash ≥ $,
     Banda drift %, Transfer minimo $, Cooldown prelievi (ore, ×60 → minuti);
   - toggle "Blocca prelievi durante blocco drawdown".
2. **`GlobalPane`** — card "🏦 Bank · Riserva" (mostrata quando
   `reserve_value_usd > 0`): valore + P&L %, **Tradabile vs Totale**, P&L totale
   combinato; blocco **Volatility budget** (max drawdown e vol giornaliera,
   trading vs portafoglio totale) quando `volatility_budget.status === "ready"`.
3. **`EquityChart`** — toggle **"Solo trading" / "Portafoglio totale"** (visibile
   solo se i punti hanno `portfolio_pnl_pct`); in modalità portafoglio la curva
   usa `portfolio_pnl_pct` e l'etichetta diventa "PnL portafoglio". Stato del
   toggle in `GlobalPane`.

## SCOSTAMENTI DAL PIANO

- **`reserve_events`**: il toggle è cablato lato backend (default ON, round-trip
  via `/api/v1/notifications/preferences`) ma **l'app non ha una UI delle
  preferenze notifiche** — aggiungerla è un task a sé, fuori dallo scope della
  riserva. Nessuna modifica a `SettingsTab.tsx`.

## COSA È STATO VERIFICATO

- `npx tsc --noEmit -p tsconfig.app.json` → exit 0.
- `npx eslint src/components/AgentTab.tsx` → **6 errori, identici al tree pulito**
  (debito React pre-esistente). Zero nuovi errori.
- Backend: `pytest backend/tests` → **347 passati** (+1: test `/transactions`),
  1 skip, **15 falliti = identici sul tree pulito**. Zero regressioni.
- Verifica visiva non eseguita (build frontend caricherebbe `.env` reale, vietato
  da AGENTS.md). Layout allineato al mockup `bank-mockup.html`.

## STATO DELIVERABLE

- `src/components/AgentTab.tsx`, `backend/tests/unit/test_reserve_api.py` — modificati.
- Doc: `PROJECT_STRUCTURE.md`, plan aggiornati.
- **R7 completo.** Prossimo step: **R8** (report riepilogativo + verifica
  startup/guardrail; `PROJECT_STRUCTURE.md` già aggiornato lungo il percorso).

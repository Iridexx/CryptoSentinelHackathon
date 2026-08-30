# Piano — Scheda "Riserva di Valore" (sotto Agente)

Stato: BOZZA IN DISCUSSIONE — non iniziare l'implementazione senza approvazione esplicita (AGENTS.md §Required Documentation).

Ultimo aggiornamento: 2026-08-30 (2ª revisione: modello sweep/deploy a due fasi con saldo USDC, fix double-count del cash, contabilità fee deploy)

---

## 1. OBIETTIVO

Una **Riserva di Valore**: sotto-portafoglio dove l'utente sposta parte dell'equity
in hard asset (BTC, ETH, SOL, TRX, BNB — token wrapped/Binance-Peg ammessi),
acquistati spot. Il mark-to-market della riserva entra nella % di P&L complessiva
del portafoglio. Scopo: fare da **zavorra stabile** rispetto al book di trading
(≈148 token, molti micro-cap ad alta volatilità) e ridurre nel tempo la
volatilità/drawdown complessivo.

La scheda vive come **nuovo pane `bank` ("Bank") dentro `AgentTab`** (non una nuova
voce di Navbar), con pulsante dedicato a tutta larghezza sotto le due righe di
pulsanti esistenti (D10). Config dedicata in una sotto-scheda "Bank" di Setup (D11).

---

## 2. DECISIONI CONFERMATE (2026-08-30)

| # | Tema | Decisione |
|---|---|---|
| D1 | Fonte capitale | **Scorporato dall'equity.** Un `transfer_in` sposta USD dall'equity tradabile alla riserva. Equity totale invariata, si segmenta. Il capitale a rischio del bot cala. |
| D2 | Guardrail drawdown -15% | **Riserva ESCLUSA dal guard** che ferma l'agente (si calcola solo sul book di trading). La riserva compare in un **totale combinato** ma non fa scattare né evita il blocco. |
| D3 | Esecuzione/valutazione | **Simulata a prezzi reali** (come il resto in `dry_run`): acquisti registrati al prezzo live + fee modellata, MTM con market-data reale. Percorso predisposto per il live futuro. |
| D4 | Ribilanciamento | **Due bande** (rivisto da D29): `drift_band_pct` (5%) = solo **indicatore visivo** nella UI (asset fuori banda evidenziato) e priorità del deploy; `rebalance_band_pct` (~12%) = soglia che fa scattare il `rebalance()` **con vendita** del sovrappeso (raro). Il deploy (§8ter) fa già il ribilanciamento lato acquisti in continuo. |
| D5 | Composizione riserva | **5 hard asset** (BTC/ETH/BNB/SOL/TRX, pesi 40/30/20/5/5) **+ un saldo USDC di transito** (D29). L'USDC non è una sleeve strategica: è liquidità che sta lì solo tra sweep (accumulo) e deploy (acquisto). I pesi target sommano a 100 sui 5 asset; l'USDC è mostrato a parte. |
| D6 | Sweep automatico profitti | **IN SCOPE.** Versamento periodico di una % dei profitti *realizzati* dal trading nella riserva (profit ratchet). Configurabile, disattivabile. Vedi §8bis. |
| D7 | Cooldown / lock prelievi | **IN SCOPE.** `transfer_out` soggetto a cooldown; inoltre bloccato mentre il guard di drawdown di trading è attivo (permesso solo `transfer_in`). |
| D8 | Benchmark riserva | **IN SCOPE.** La vista confronta la riserva con "solo BTC hold" e con il book di trading. Vedi §6bis. |
| D9 | Volatility budget | **IN SCOPE.** Vista che mostra drawdown/volatilità del portafoglio con e senza riserva. Vedi §6bis. |
| D10 | Naming + UI | Il pane nella schermata Agente si chiama **"Bank"**. Il pulsante è **a tutta larghezza** (= somma dei 3 pulsanti di una riga), collocato **sotto** le due righe da 3 pulsanti esistenti, con stile in evidenza (accent, più alto). |
| D11 | Parametri configurabili | **Tutti** i parametri della riserva (pesi target, banda drift, sweep %/intervallo, cooldown, min transfer, toggle) sono editabili in una **nuova sotto-scheda "Bank" dentro Setup**. Pattern doppio come `AgentMobileSettings`: default in `configs/reserve.yaml`, override runtime persistito e applicato live. |
| D12 | Pesi target | **40/30/20/5/5** BTC/ETH/BNB/SOL/TRX. |
| D13 | Sweep default | **20% ogni 24h** (configurabile via scheda Bank). |
| D14 | Cooldown default | **24h + blocco durante il guard drawdown** (configurabile via scheda Bank). |
| D16 | Etichetta pulsante | **"🏦 Bank · Riserva"** (come nel mockup), a tutta larghezza sotto le due righe. |
| D17 | Grafico pane Bank | **Rendimento % con 3 linee benchmark** (riserva / solo-BTC / trading) + toggle per passare al **valore assoluto $** nel tempo. |
| D18 | Scope pesi asset | Pesi **dentro la riserva** (per il ribilanciamento) **+ una riga** "riserva = X% del portafoglio totale". Niente doppia colonna. |
| D19 | Volatility budget | Nel **pane Global** (sintesi accanto agli altri numeri di portafoglio). |
| D20 | Confermati salvo obiezione | admin-only per transfer/rebalance manuale; durante il drawdown guard solo `transfer_in` (mai `transfer_out`); il reset analytics (`archive_dry_run`) archivia e svuota anche la riserva; ordine pane Bank = valore → grafico → pesi → posizioni → movimenti → azioni. |
| **D21** | **Solo profitti nella riserva** | Nella riserva si può spostare **solo il guadagno oltre l'`initial_equity`**. Limite di ogni `transfer_in` (manuale **e** sweep) = `max(0, tradable_equity − initial_equity)`. Se `tradable_equity ≤ initial_equity` → nessun versamento in riserva finché il bot non torna sopra l'`initial_equity`. Il capitale iniziale non entra mai nella riserva. Vedi §7bis. |
| D22 | Disattivazione con asset dentro | Toggle "Riserva attiva" → OFF con holdings presenti = **congela**: stop sweep, deploy, ribilancio (auto e manuale) e **transfer_in manuale**. Holdings/valore restano e continuano il MTM. Nessuna vendita automatica. Solo `transfer_out` e valutazione/snapshot continuano. Riattivabile. |
| D23 | Notifiche | Push per eventi **importanti**: sweep eseguito, ribilancio eseguito, transfer manuale. Nuova categoria nelle preferenze notifiche (`NotificationPreferences` + `AgentNotifier`), toggle dedicato. Avvisi "asset fuori banda" NON notificati (solo log/UI). |
| D24 | Volatility budget | Confermato nel **pane Global** (D19/D9). Posizione fine da rivedere quando il pane Global sarà da alleggerire. |
| **D25** | **Contabilità equity (fix)** | `tradable_equity = total_equity_usd − reserve_transferred_net_usd` (NON `− reserve_value_usd`). `reserve_transferred_net_usd` = contatore su `PortfolioState`: Σ(cash entrato via sweep/transfer_in) − Σ(cash uscito via transfer_out). **Sweep e transfer non hanno fee** (spostano solo cash). Le **fee del deploy** (cash→asset) NON riducono il contatore: sono un *drag sul P&L della riserva* (`reserve_value < cost_basis`), come le fee di trading sul `pnl_usd`. Così il sizing del risk manager non si muove quando il mercato muove la riserva. Vedi §6. |
| ~~D26~~ | ~~Niente cassa interna~~ | **ANNULLATA da D29.** La riserva ha un saldo USDC persistito (`reserve_cash_usd`), è il buffer tra sweep e deploy. Campi su `PortfolioState`: `reserve_cash_usd`, `reserve_transferred_net_usd`, `last_swept_realized_pnl_usd`, `last_deploy_at`, `reserve_frozen` — via `extra_json` o colonne col pattern `upgrade_schema`. |
| **D29** | **Sweep vs Deploy (due fasi)** | **Sweep** (ogni `sweep_interval_hours`, default 24): sposta `sweep_pct`% del nuovo profitto realizzato da equity tradabile → **saldo USDC** della riserva. Nessun acquisto, nessuna fee. **Deploy** (batch, §8ter): investe il saldo USDC quando (a) passati `deploy_interval_days` (default 7) **oppure** (b) saldo USDC ≥ `deploy_min_cash_usd` (**default $40**). Compra gli asset ordinati per **gap relativo** (`gap$/target$`), ogni acquisto ≥ `deploy_min_buy_usd` ($5); chi non raggiunge $5 è **rimandato** al deploy dopo (il suo gap cresce, la priorità sale → nessun asset resta escluso per sempre, max 1–2 cicli). Resto < $5 → resta cash. `rebalance()` (vendita del sovrappeso) resta ma raro (banda larga). Fee wrapped BSC/PancakeSwap basse (LP 0.25% + gas in centesimi): il floor $5 tiene l'overhead gas < ~6%. |
| D27 | Benchmark: riuso | Il benchmark BTC riusa `_btc_benchmark(snapshots)` già in `api/routes/views.py` (gestisce già il clock simulato dry-run). `trading_pct` dai `PnlSnapshot`. Calcolato a read-time, non salvato. |
| D28 | Volatility budget: soft | Consegnato ma mostra "dati insufficienti" (come lo Sharpe) finché non c'è abbastanza storico di snapshot giornalieri. |
| **D30** | **Tracking fee riserva** | Ogni movimento con costo registra `ReserveTransaction.fee_usd` (swap + slippage + gas modellato). `ReserveRepository.sum_fees(user_id)` → `reserve_fees_total_usd` in `ReserveView`/`GlobalView`, mostrato nel pane Bank ("Fee pagate: $X"). Le stesse fee si sommano al `total_fees_usd` del portafoglio. `ReserveSnapshot` opzionalmente tiene `fees_cumulative_usd` per il grafico. |
| D15 | SOL/TRX | **R1b ESEGUITO (2026-08-30).** Aster spot esiste (`sapi.asterdex.com/api/v1/exchangeInfo`, 68 coppie, quasi tutte memecoin/nuove listing). Coppie spot USDT presenti per **BTC, ETH, BNB, SOL**; **TRX assente da Aster spot** (solo perp). Aster spot **non è cablato** nel codice (solo host futures) → integrarlo = nuovo venue. Decisione: fase simulata usa i prezzi del market-data provider (tutti e 5 gli asset OK, TRX incluso). Per il live: **PancakeSwap** come venue primario per tutti e 5 (BTCB/ETH/WBNB + Binance-Peg SOL/TRX); Aster spot resta opzione futura per BTC/ETH/BNB/SOL. TRX live dipende dalla liquidità Binance-Peg su PancakeSwap — da verificare al passaggio live, altrimenti si sostituisce/rimuove. |

---

## 3. VINCOLI ARCHITETTURALI DA RISPETTARE

- **Config**: unico loading point `backend/app/core/config.py`. Nuovo
  `configs/reserve.yaml` versionato, letto solo via `Settings`, con la precedenza
  standard (env > instance.yaml > YAML funzionali > default Pydantic).
- **`eligible_tokens.yaml` NON si tocca** (guardrail hard nel codice: 100–200 voci,
  "trades outside the eligible-token universe must not be allowed"). Gli asset di
  riserva vivono in una lista separata in `reserve.yaml`. La riserva **non** è un
  "trade": è allocazione di tesoreria, fuori dal universo operativo dell'agente.
- **Separazione domini** Spot / Perp / Global preservata → nuovo dominio `reserve`.
- **`user_id` ovunque** (ready-for-multi-user).
- **Auth**: letture con read-token; ogni azione che muove capitale o cambia config
  (transfer, pesi target, rebalance manuale) = **admin-only**.
- **Codice e commenti backend in inglese**; i18n it/en aggiornata.
- **Venue reale**: `venues/aster` è solo perp (`/fapi/`, read-only). Per gli hard
  asset spot la via reale è **PancakeSwap** (`PancakeSwapProvider`, già fa swap
  on-chain, `build_path`, fee/slippage in `spot_fees.py`) con indirizzi BEP20
  curati (BTCB, ETH, WBNB, SOL-peg, TRX-peg). Aster spot = integrazione separata,
  fuori scope ora.
- **Windows**: test con `backend\.venv\Scripts\python.exe` dalla root.
- A fine step: aggiornare `docs/PROJECT_STRUCTURE.md` + report in `docs/reports/`.

---

## 4. MODELLO DATI (backend)

Nuovo package `backend/app/domain/reserve/` + ORM in `persistence/models/reserve.py`:

### `ReserveHolding` (posizione corrente per asset)
| campo | tipo | note |
|---|---|---|
| id | int PK | |
| user_id | str(36) idx | |
| asset | str | simbolo logico: BTC, ETH, SOL, TRX, BNB |
| venue | str | `pancakeswap` (default), predisposto per altri |
| quantity | Numeric(38,18) | quantità detenuta |
| avg_cost_usd | Numeric(20,8) | costo medio di carico (per P&L MTM) |
| updated_at | DateTime(tz) | |

Unique: `(user_id, asset)`.

### `ReserveTransaction` (movimenti — audit trail)
| campo | tipo | note |
|---|---|---|
| id | int PK | |
| user_id | str(36) idx | |
| type | str | `transfer_in` \| `transfer_out` \| `sweep` \| `deploy_buy` \| `rebalance_buy` \| `rebalance_sell` |
| asset | str \| null | null per i movimenti di sola cassa (`transfer_in`, `sweep`) |
| quantity | Numeric(38,18) \| null | |
| price_usd | Numeric(20,8) \| null | prezzo eseguito (simulato = prezzo live) |
| value_usd | Numeric(20,8) | controvalore USD del movimento |
| fee_usd | Numeric(20,8) | costo all-in del movimento: swap + slippage + gas modellato (0 per `sweep`/`transfer_in`) |
| cash_usd_delta | Numeric(20,8) | effetto sul saldo USDC della riserva |
| venue | str \| null | |
| ref | str \| null | tx hash quando live; null in simulato |
| created_at | DateTime(tz) idx | |

### `ReserveSnapshot` (serie storica per il grafico andamento — clone di `PnlSnapshot`)
| campo | tipo | note |
|---|---|---|
| id | int PK | |
| user_id | str(36) idx | |
| timestamp_utc | DateTime(tz) idx | cadenza oraria (allineata allo slow tick) |
| total_value_usd | Numeric(20,8) | `reserve_cash_usd` + MTM dei 5 asset |
| cash_usd | Numeric(20,8) | saldo USDC allo snapshot |
| cost_basis_usd | Numeric(20,8) | `reserve_transferred_net_usd` allo snapshot |
| pnl_usd | Numeric(20,8) | total_value − cost_basis |
| holdings_json | Text | `[{asset, qty, price_usd, value_usd, weight_pct}]` (5 asset) |

### Saldo USDC + due fasi (D29)
- **Sweep**: equity tradabile → `reserve_cash_usd` (USDC). Movimento contabile,
  nessuna fee.
- **Deploy**: `reserve_cash_usd` → acquisto dei 5 asset (fee modellata/reale).
- **Transfer In manuale**: aggiunge a `reserve_cash_usd` + tenta subito un deploy
  di quanto supera `deploy_min_buy_usd`.
- **Transfer Out**: prima svuota `reserve_cash_usd`, poi vende asset pro-rata per
  il resto; accredita al tradabile.

### Contabilità su `PortfolioState` (D25/D29)
In `extra_json` (zero migration) o colonne col pattern `upgrade_schema`:
| campo | uso |
|---|---|
| `reserve_cash_usd` | saldo USDC di transito (parte di `reserve_value_usd`). |
| `reserve_transferred_net_usd` | Σ(transfer_in) − Σ(transfer_out) al netto fee. Costo di carico; è il numero sottratto dal tradabile (D25). |
| `last_swept_realized_pnl_usd` | high-water mark del P&L realizzato di trading all'ultimo sweep. |
| `last_deploy_at` | timestamp ultimo deploy (per il trigger dei 7 giorni). |
| `reserve_frozen` | bool — riserva congelata (D22). |

---

## 5. SERVIZI (backend)

### `ReserveService` (`domain/reserve/service.py`)
- `get_view(user_id) -> ReserveView` — holdings MTM, pesi correnti vs target, P&L,
  `reserve_transferred_net_usd`, capacità di versamento (§7bis), stato `frozen`.
- `get_history(user_id, range) -> list[ReserveSnapshotPoint]` — serie `ReserveSnapshot`
  + `reserve_pct` / `btc_hold_pct` / `trading_pct` calcolati a read-time (D27).
- `transfer_in(user_id, amount_usd) -> ReserveView` — admin. Bloccato se `frozen`.
  Importo capato a `max(0, tradable_equity − initial_equity)` (§7bis); scala il
  contatore, accredita `reserve_cash_usd`, poi `deploy()` immediato di quanto
  supera `deploy_min_buy_usd`.
- `transfer_out(user_id, amount_usd) -> ReserveView` — admin. Prima svuota
  `reserve_cash_usd`, poi vende asset **pro-rata** per il resto; riaccredita il
  tradabile (contatore −). Soggetto a cooldown e blocco durante il guard drawdown.
- `set_target_weights(user_id, weights)` — admin. Validazione: somma = 100%.
- `run_profit_sweep(user_id)` — §8bis (accredita solo `reserve_cash_usd`).
- `deploy(user_id, force=False) -> ReserveView` — §8ter. Investe `reserve_cash_usd`
  negli asset più sotto-peso. Bloccato se `frozen` o `hard_stop`.
- `rebalance(user_id, dry_run=False) -> RebalancePlan|ReserveView` — admin manuale
  + scheduler solo quando la deriva supera una **banda larga** (vende il
  sovrappeso). Bloccato se `frozen` o `hard_stop`.
- `valuate(user_id)` — ricalcola MTM di ogni holding (market-data provider /
  `ohlcv_sources`).
- `snapshot(user_id)` — scrive `ReserveSnapshot` (orario).
- `set_frozen(user_id, bool)` — chiamato dal toggle "Riserva attiva" (D22).

**`initial_equity` fallback**: se `PortfolioState` non esiste ancora (primo avvio,
ramo `portfolio is None` di `global_view`) → usa `Settings.dry_run_capital_usd`.

**Atomicità/concorrenza**: ogni transfer/sweep/rebalance in **un solo commit**
(holdings + righe `ReserveTransaction` + contatore `PortfolioState`), stessa
disciplina di sessione async del resto (il progetto ha avuto lock SQLite). Lo
slow-tick `valuate`/`snapshot` non modifica holdings, solo legge + scrive snapshot.

### `ReserveExecutor` (`domain/reserve/executor.py`)
Adapter unico per gli acquisti/vendite. **R2–R9 consegnano solo il ramo simulato**:
- `execution_mode == dry_run` (default): registra al prezzo live del market-data,
  fee = `spot_fees.estimate(...)`. Nessuna tx on-chain.
- `execution_mode == live`: **stub che solleva `NotImplementedError` fino a R10**
  (gli indirizzi in `reserve.yaml` sono mainnet, il live è gated a testnet →
  serve prima la storia indirizzi/rete). Il ramo delegherà a `PancakeSwapProvider`
  riusando `gas.py` / `approvals.py`.

### Repository `ReserveRepository` (`persistence/repositories/reserve.py`)
CRUD holdings, append transaction, save/list snapshot, get/set saldo e target
weights, `sum_fees(user_id, since=None)` (D30).

---

## 6. INTEGRAZIONE CON LE VISTE / P&L

### `GlobalView` — nuovi campi (schema `schemas/views.py`)
| campo | formula |
|---|---|
| `reserve_value_usd` | `reserve_cash_usd` + MTM dei 5 asset |
| `reserve_cash_usd` | saldo USDC in attesa di deploy |
| `reserve_cost_basis_usd` | `reserve_transferred_net_usd` (costo di carico) |
| `reserve_pnl_usd` | `reserve_value_usd − reserve_cost_basis_usd` |
| `reserve_pnl_pct` | `reserve_pnl_usd / reserve_cost_basis_usd` (0 se cost_basis = 0) |
| `reserve_fees_total_usd` | `ReserveRepository.sum_fees(user_id)` — fee cumulate della riserva (D30) |
| `tradable_equity_usd` | **`total_equity_usd − reserve_transferred_net_usd`** (D25) — NON `− reserve_value_usd` |
| `total_portfolio_equity_usd` | `tradable_equity_usd + reserve_value_usd` |
| `total_portfolio_pnl_pct` | `(total_portfolio_equity_usd − initial_equity_usd) / initial_equity_usd` |

### Come "il quantitativo influisce sulla % di P&L" (D1 + D2 + D25)
- `initial_equity_usd` **invariato** dal transfer (interno, non chiama `EquityAdjustment`).
- `tradable_equity` si muove **solo** su transfer/sweep (il contatore), non quando
  il mercato muove la riserva → il sizing del risk manager resta stabile.
- `total_portfolio_pnl_pct` = P&L trading + P&L riserva, tutto su `initial_equity`.
- Il **P&L di trading** di oggi (`pnl_total_pct`) resta sul solo book di trading →
  il guard drawdown −15% non vede la riserva (D2).
- La UI Global mostra due numeri: "P&L Trading" e "P&L Totale (con Riserva)".
- **Fee della riserva** (D30): solo `deploy_buy` / vendite `transfer_out` /
  `rebalance` (sweep e transfer_in = 0). Tracciate per movimento in
  `ReserveTransaction.fee_usd`, aggregate in `reserve_fees_total_usd`, sommate al
  `total_fees_usd` del portafoglio, e già riflesse nel `reserve_pnl` (valore <
  costo di carico).

### `ViewService.global_view`
Aggiungere lettura riserva (repo) e calcolo dei campi sopra. `_risk_guardrail(...)`
continua a ricevere **solo** l'equity/drawdown di trading (nessuna modifica al
trigger).

---

## 6bis. BENCHMARK + VOLATILITY BUDGET (D8, D9)

Sfruttano dati già presenti (`ReserveSnapshot`, `PnlSnapshot`, prezzi BTC dal
market-data provider / `ohlcv_sources`).

### Benchmark riserva (D27)
Endpoint history, per ogni punto snapshot, calcolato **a read-time** (non salvato):
- `reserve_pct` — rendimento cumulato della riserva dal primo snapshot.
- `btc_hold_pct` — **riuso di `_btc_benchmark(snapshots)`** già in
  `api/routes/views.py` (allinea il % BTC agli snapshot e gestisce già il clock
  simulato dry-run).
- `trading_pct` — dai `PnlSnapshot` nello stesso periodo.
Il grafico sovrappone le tre linee (stesso pattern di `EquityChart`).

### Volatility budget (D28 — soft)
Blocco nel pane Global:
- std dei rendimenti giornalieri e max drawdown su (1) solo trading, (2) totale.
- delta: "la riserva ha ridotto il max drawdown da X% a Y%".
- Backend in `ViewService` (riuso di `_daily_sharpe` / logica drawdown su serie
  combinata), campo `volatility_budget` in `GlobalView`.
- Mostra **"dati insufficienti"** (come lo Sharpe: `sharpe_status`) finché non c'è
  abbastanza storico. Non è affidabile per le prime settimane.

---

## 7. INTEGRAZIONE CON IL RISK MANAGER

- Il sizing delle posizioni (`capital_per_trade_pct`, `per_trade_pct`,
  `max_total_exposure_pct`) deve lavorare su **`tradable_equity`**, non su
  `total_equity`. → un solo punto da cambiare: la sorgente equity nel risk manager
  (`agent/risk/`). Spostare in riserva riduce automaticamente le size: è il
  meccanismo che abbassa la volatilità.
- `min_portfolio_value_usd` (floor hard $5): resta riferito a **`tradable_equity`**.
  Con la regola §7bis (D21) il floor è comunque protetto di riflesso — un
  `transfer_in` non può mai portare `tradable_equity` sotto `initial_equity`, che
  è molto sopra $5. Nessun bisogno di un secondo check.
- La riserva **non** apre "posizioni" nel senso del risk manager e non conta nel
  `max_open_positions`.

---

## 8. SCHEDULER / SLOW TICK

Nel loop lento dell'agente (`agent/service.py`), aggiungere un passo:
1. `ReserveService.valuate(user_id)` — MTM (cash + asset).
2. Ogni ora: `ReserveService.snapshot(user_id)`.
3. Se `sweep_enabled` e trascorse `sweep_interval_hours` → `run_profit_sweep()` (§8bis, solo cash).
4. Se trigger di deploy (§8ter: 7 giorni **o** cash ≥ soglia) → `deploy()`.
5. *(opzionale R6)* Se `auto_rebalance` e deriva oltre `rebalance_band_pct` →
   `rebalance()` con vendita del sovrappeso (raro). Altrimenti solo manuale.
Passi 3–5: notifica tipizzata via `AgentNotifier` (D23), chiave idempotenza =
`ReserveTransaction.id`.

Il kill switch **hard_stop** sospende sweep, deploy e rebalance automatici (non i
`transfer_out` manuali admin). Se la riserva è **congelata** (D22): saltati passi
3–5 + `transfer_in` + ribilancio manuale; restano valutazione/snapshot (1, 2) e i
soli `transfer_out`.

---

## 7bis. REGOLA: SOLO PROFITTI NELLA RISERVA (D21)

Vincolo che governa **ogni** `transfer_in` (manuale via UI **e** sweep automatico):

```
capacità_versamento = max(0, tradable_equity − initial_equity)
importo_effettivo    = min(importo_richiesto, capacità_versamento)
```

- `initial_equity` = `PortfolioState.initial_equity_usd` (già ribaselinato dai
  versamenti/prelievi reali via `EquityAdjustment`; il transfer verso la riserva
  NON lo tocca).
- `tradable_equity` = equity del book di trading (esclusa la riserva).
- Se `tradable_equity ≤ initial_equity` → `capacità_versamento = 0`: nessun
  versamento finché il bot non torna in utile sopra la base.
- Conseguenza: il **capitale iniziale non entra mai** nella riserva; la riserva è
  fatta solo di guadagni "messi al sicuro". Il floor hard ($5) è protetto di
  riflesso (non si può scendere sotto `initial_equity`, molto più alto).
- `transfer_out` non è soggetto a questo limite (aumenta solo `tradable_equity`);
  resta soggetto a cooldown e blocco durante il guard drawdown.
- UI: il campo importo in "Sposta capitale" mostra "Disponibile da spostare:
  $X.XX" = `capacità_versamento`; se 0, il pulsante è disabilitato con nota
  "nessun profitto sopra il capitale iniziale".
- `sweep_min_tradable_equity_usd` (introdotto in R1) è **superato** da questa
  regola → rimosso da config/schema in R4.

---

## 8bis. SWEEP AUTOMATICO DEI PROFITTI (D6, D29)

"Profit ratchet": quota dei profitti realizzati spostata dall'equity tradabile al
**saldo USDC** della riserva. Nessun acquisto (quello è il deploy, §8ter).

- Base: **incremento del P&L realizzato di trading** dall'ultimo sweep
  (`last_swept_realized_pnl_usd`, high-water mark). Solo incrementi positivi.
- Quota: `sweep_pct` del delta positivo (default 20%, D13), capata da §7bis
  (`max(0, tradable_equity − initial_equity)`).
- Vincoli: rispetta `min_transfer_usd`; sospeso da `hard_stop` / guard drawdown /
  riserva congelata (D22).
- Cadenza: `sweep_interval_hours` (default 24).
- `ReserveTransaction(type="sweep", ...)` + notifica `AgentNotifier` (D23).
- Disattivabile (`sweep_enabled: false`).

---

## 8ter. DEPLOY DEL SALDO USDC (D29)

Investe `reserve_cash_usd` nei 5 asset, in batch e raramente.

### Parametri (config)
| | default | |
|---|---|---|
| `deploy_interval_days` | 7 | trigger a tempo |
| `deploy_min_cash_usd` | 40 | trigger a soglia |
| `deploy_min_buy_usd` | 5 | acquisto singolo minimo (overhead gas < ~6%) |

### Algoritmo
1. Skip se `frozen` / `hard_stop`. `cash = reserve_cash_usd`; skip se `cash < deploy_min_buy_usd`.
2. Trigger: `cash ≥ deploy_min_cash_usd` **oppure** `now − last_deploy_at ≥ deploy_interval_days`. Altrimenti skip.
3. `base = reserve_value_usd` (**già include il cash** — non sommarlo di nuovo).
   Per asset: `target$ = weight × base`, `valore_corrente$` = MTM dell'asset
   (senza cash), `gap$ = max(0, target$ − valore_corrente$)`, `gap_rel = gap$ / target$`.
4. Ordina per **`gap_rel` desc** (tie-break: peso target desc). Scarta `gap$ = 0`.
5. Scendendo per priorità, riempi ogni asset fino al **suo gap$** prendendo dal
   cash rimanente (greedy, niente ripartizione proporzionale — così un gap
   minuscolo su un asset non affama un vero sotto-peso). Se `min(gap$, cash_residuo)
   < deploy_min_buy_usd` → l'asset **salta il giro**, il cash resta.
6. Se nessuna fetta qualifica **e** il trigger è a tempo → tutto il cash sull'asset
   con `gap_rel` massimo se ≥ `deploy_min_buy_usd`, altrimenti lascia tutto in cash.
7. Esegui gli acquisti. **Il cash non impiegato resta `reserve_cash_usd`** (si
   somma agli sweep successivi). Aggiorna `last_deploy_at`.
   `ReserveTransaction(type="deploy_buy", asset=..., ...)` per acquisto + notifica (D23).

### Dove finisce il cash saltato
Resta **nel saldo USDC della riserva** (`reserve_cash_usd`). Non torna al trading,
non gonfia gli altri asset. Si somma agli sweep successivi finché non basta a dare
≥ $5 a SOL/TRX.

### Perché SOL/TRX (5%) non restano mai fuori
Ogni deploy che compra BTC/ETH/BNB azzera il **loro** `gap_rel`; quello di SOL/TRX
resta ~100% → al giro dopo sono in cima alla lista e vengono comprati appena il
loro `gap$` accumulato (dal cash lasciato indietro + nuovi sweep) raggiunge $5
(1–2 cicli). Il trigger a 7 giorni garantisce comunque un deploy periodico
all'asset più affamato.

### Esempio ($40, riserva vuota, target 40/30/20/5/5)
Tutti `gap_rel` = 100% → tie-break sul peso → BTC $16, ETH $12, BNB $8 = **$36
investiti**. SOL e TRX ($2 < $5) saltati → **$4 restano cash**. Giro 2 (BTC/ETH/BNB
a target, `gap_rel` ≈ 0; SOL/TRX ≈ 100%): quando il cash accumulato copre ≥ $5
ciascuno, SOL e TRX vengono comprati.

---

## 9. API (`backend/app/api/routes/reserve.py`)

| metodo | path | auth | scopo |
|---|---|---|---|
| GET | `/agent/reserve` | read | `ReserveView`: holdings, pesi vs target, P&L, `transferred_net`, capacità versamento, `frozen` |
| GET | `/agent/reserve/history?range=24h\|7d\|all` | read | serie snapshot + `reserve_pct`/`btc_hold_pct`/`trading_pct` |
| POST | `/agent/reserve/transfer` | admin | `{amount_usd, direction: in\|out}` (out sempre pro-rata) |
| POST | `/agent/reserve/target-weights` | admin | `{weights: {BTC: 40, ETH: 30, ...}}` |
| POST | `/agent/reserve/rebalance` | admin | `{dry_run?: bool}` → piano o esecuzione |
| GET | `/agent/reserve/settings` | read | `ReserveSettings` effettivi (default + override) con `source` |
| POST | `/agent/reserve/settings` | admin | aggiorna gli override runtime dei parametri Bank |

Registrare il router in `api/routes/__init__.py`. In alternativa i settings possono
essere accorpati agli endpoint `mobile_agent` esistenti — da decidere in R5.

---

## 10. CONFIG — `configs/reserve.yaml`

> **R1 FATTO 2026-08-30.** `configs/reserve.yaml` reale + `ReserveConfig`/
> `ReserveAssetConfig` in `config.py` + `schemas/reserve.py` (`ReserveSettings`) +
> `domain/reserve/settings.py` (override `runtime_state` chiave `reserve_settings`).
> Struttura: scalari (`enabled`, `auto_rebalance`, `drift_band_pct`,
> `min_transfer_usd`, `rebalance_min_trade_usd`, `snapshot_interval_minutes`,
> `withdrawal_cooldown_minutes`, `block_withdrawal_during_drawdown_guard`,
> `sweep_enabled`, `sweep_pct`, `sweep_interval_hours`) + lista `assets`
> (`symbol`, `target_weight_pct`, `pancakeswap_address`, `decimals`,
> `aster_spot_symbol`). Validazione: somma pesi = 100 ±0.01, simboli unici, range
> sweep/drift.

**R3 fatto:** `reserve.yaml` aggiornato — rimosso `sweep_min_tradable_equity_usd`
(superato da §7bis), aggiunti `rebalance_band_pct` (12), `deploy_interval_days` (7),
`deploy_min_cash_usd` (40), `deploy_min_buy_usd` (5). `ReserveConfig` e
`ReserveSettings` allineati; override utente include `deploy_interval_days` e
`deploy_min_cash_usd` (`deploy_min_buy_usd` e `rebalance_band_pct` restano
yaml-only). Indirizzi BEP20 "verify" — da verificare prima di uso live.

---

## 11. FRONTEND

### `src/components/AgentTab.tsx` — pulsante "Bank" (D10)
- `type AgentPane = ... | 'bank';`
- **Non** entra nelle due `grid grid-cols-3`. Sotto di esse, un pulsante dedicato a
  tutta larghezza:
  ```tsx
  <button
    onClick={() => { hapticLight(); setPane('bank'); }}
    className={`w-full rounded-xl px-4 py-3.5 text-sm font-bold transition-colors ${
      pane === 'bank'
        ? 'bg-accent-yellow text-dark-900'
        : 'bg-accent-yellow/15 text-accent-yellow border border-accent-yellow/40'
    }`}
  >
    🏦 Bank · Riserva di Valore
  </button>
  ```
  (colore/emoji da rifinire; l'idea è: più alto, a tutta larghezza, in evidenza).
- `{pane === 'bank' && <BankPane ... />}`.

### Nuovo `BankPane` (in `AgentTab.tsx` o file dedicato)
Ordine (D20): valore → grafico → pesi → posizioni → movimenti → azioni.
1. **Header**: valore riserva (USDC + asset), P&L (USD + %), riga "riserva = X% del
   portafoglio totale" (D18), riga "USDC in attesa di deploy: $X · prossimo deploy
   tra N giorni / a $Y" (D29), riga "Fee pagate: $X" (D30). Badge "congelata" se
   disattivata con holdings (D22).
2. **Grafico andamento** (D17) — stile SVG di `EquityChart`, range 24h / 7g / Tutto
   su `/agent/reserve/history`. Default: rendimento % con 3 linee (riserva /
   solo-BTC / trading); toggle per passare al **valore assoluto $**.
3. **Grafico pesi** — donut/bar SVG: peso corrente vs target per asset (pesi
   *dentro* la riserva), evidenzia gli asset fuori banda di drift.
4. **Posizioni**: asset, quantità, valore, peso %, costo medio, P&L MTM.
5. **Movimenti**: lista `ReserveTransaction` (tipo, asset, valore, fee, data).
6. **Azioni admin** (solo con admin token, pattern identico a "Liquidità" in Setup):
   - Transfer In: mostra "Disponibile da spostare: $X.XX" = `max(0, tradable −
     initial)` (§7bis/D21); pulsante disabilitato se 0.
   - Transfer Out: solo importo (svuota prima il cash USDC, poi vende asset
     pro-rata — automatico, nessun selettore); disabilitato durante il guard
     drawdown e nel cooldown (mostra il tempo rimanente).
   - **Deploy ora** (investe subito il saldo USDC) + Rebalance ora (anteprima `dry_run`).
   - I pesi target si modificano nella scheda Setup › Bank (link).

### `src/services/agentApi.ts`
Aggiungere `fetchReserveView`, `fetchReserveHistory`, `reserveTransfer`,
`setReserveTargetWeights`, `reserveRebalance` + tipi `ReserveView`,
`ReserveHolding`, `ReserveSnapshotPoint`, `ReserveTransactionRow`.

### Setup — nuova sotto-scheda "Bank" (D11)
`SetupPane` ha già un `setupTab` (`'sistema' | 'strategia' | ...`). Aggiungere
`'bank'` con i controlli (riuso di `NumberInput` / `ToggleInput` / `SelectInput`
già presenti):
- Toggle `Riserva attiva` (OFF con holdings dentro = congela, D22),
  `Ribilanciamento automatico`, `Sweep profitti automatico`.
- Pesi target per asset (5 `NumberInput`, con indicatore "somma = 100%").
- `Sweep %`, `Sweep ogni (ore)`.
- `Deploy ogni (giorni)`, `Deploy se cash ≥ $` (D29).
- `Min transfer $`, `Cooldown prelievi (ore)`, toggle `Blocca prelievi durante blocco drawdown`.
- Lista asset/venue in **sola lettura** (esito R1b: TRX senza Aster spot).
Salvataggio con lo stesso flusso `handleSave` / dirty-flag e admin token degli
altri settings.

### Notifiche (D23)
- `NotificationPreferences` (schema + UI in `SettingsTab`): nuovo toggle
  `reserve_events` (default ON).
- `AgentNotifier`: nuovi tipi push idempotenti — `reserve_sweep`,
  `reserve_rebalance`, `reserve_transfer`. Avvisi "asset fuori banda" NON
  notificati.

### `GlobalPane`
Aggiungere una `Stat` "Bank", mostrare "Equity tradabile" vs "Totale con Riserva",
e il blocco **volatility budget** (§6bis / D24). Posizione fine da rivedere quando
il pane sarà da alleggerire.

### i18n
Nuove chiavi in `backend/app/i18n/locales/{en,it}.json` e stringhe frontend —
**inglese come base**, italiano preservato (regola AGENTS.md).

### Onboarding
Nessun requisito: la riserva funziona in dry-run senza credenziali. Nessun check
aggiunto al flusso `validateOnboarding`.

### Dashboard
Mirror = **step R9** (dopo la parte mobile), come per le altre feature mobile-first.

---

## 12. TEST (`backend/tests/unit/test_reserve.py`)

- Config: `reserve.yaml` valido → Settings OK; somma pesi ≠ 100 → ValidationError. *(R1 fatto)*
- **§7bis**: `transfer_in` capato a `max(0, tradable − initial)`; con
  `tradable ≤ initial` → richiesta rifiutata; con profitto $30 e richiesta $50 →
  spostati $30.
- **Sweep** (D29): delta realizzato +$100, `sweep_pct` 20 → `reserve_cash_usd`
  += $20, **nessun acquisto**; delta negativo → niente; `hard_stop` → saltato.
- **Deploy** (D29): cash $40, holdings vuoti → BTC $16 / ETH $12 / BNB $8 investiti,
  **$4 restano `reserve_cash_usd`** (quota SOL/TRX saltata, NON redistribuita).
  Giro 2: `gap_rel` SOL/TRX ≈ 100% → primi in lista, comprati quando il cash ≥ $5 ciascuno.
- Deploy con cash $3 → nessun acquisto (< `deploy_min_buy_usd`), i $3 restano cash.
- Quota saltata: mai spostata sugli altri asset (niente sovrappeso), sempre → cash.
- Deploy trigger a tempo (7 giorni), cash sotto soglia ma ≥ $5 → tutto sull'asset
  con `gap_rel` massimo (garantisce che nessun asset resti fuori all'infinito).
- `transfer_in`: cash += importo, deploy immediato del deployabile; bloccato se `frozen`.
- `transfer_out`: svuota prima il cash, poi vende asset pro-rata; NON soggetto a §7bis.
- Deploy `base` = `reserve_value_usd` (cash **già** incluso, no doppio conteggio).
- Deploy fee: NON tocca `reserve_transferred_net_usd`; appare come `reserve_pnl` negativo.
- Cooldown prelievo: secondo `transfer_out` entro la finestra → rifiutato.
- `transfer_out` con guard drawdown attivo → rifiutato; `transfer_in`/sweep OK.
- Riserva congelata (D22): sweep, deploy, rebalance, `transfer_in` bloccati;
  `valuate`/`snapshot` e `transfer_out` continuano.
- Benchmark: serie history espone `reserve_pct` / `btc_hold_pct` / `trading_pct`.
- Volatility budget: max drawdown combinato ≤ max drawdown del solo trading quando
  la riserva è meno volatile.
- `valuate` + MTM: prezzo raddoppia → `reserve_pnl_usd` coerente.
- Pesi: deriva oltre `rebalance_band_pct` → `rebalance` genera piano che vende il
  sovrappeso e riporta ai target. Deriva sotto la banda → nessuna vendita.
- `reserve_pnl_pct` con `cost_basis = 0` → 0 (niente div/0).
- Deploy `base` non doppia il cash: `$40` cash su riserva vuota → `target BTC = $16`
  (non $32).
- **D25**: `tradable_equity = total_equity − reserve_transferred_net_usd`; raddoppio
  del prezzo di un asset riserva → `tradable_equity` **invariato**, `reserve_pnl`
  cambia, `_risk_guardrail` non cambia (D2).
- Risk manager: sizing calcolato su `tradable_equity` (contatore, non MTM).
- Contabilità (D25/D30): `transfer_in $50` (fee 0) → `reserve_transferred_net_usd`
  += 50, cash += 50. Poi `deploy_buy` $16 con fee $0.05 → BTC per $15.95,
  `reserve_transferred_net_usd` invariato (50), `reserve_fees_total_usd` += 0.05,
  `total_fees_usd` += 0.05, `reserve_pnl` = −0.05.
- `sum_fees`: 3 `deploy_buy` da $0.05 + 1 `transfer_out` sell da $0.10 →
  `reserve_fees_total_usd` = $0.25.
- Primo avvio (no `PortfolioState`): `initial_equity` fallback = `dry_run_capital_usd`.
- Reset (`archive_dry_run`): tabelle riserva archiviate + `PortfolioState` reserve
  fields azzerati (R4b).
- Concorrenza: transfer durante lo slow-tick → nessun holding corrotto (commit atomico).
- Auth: `transfer` con read-token → 403.
- Import/startup backend OK; guardrail hard invariati (148 eligible tokens).

---

## 13. QUESTIONI APERTE / NOTE

Riferimento visivo: mockup `bank-mockup.html` (artifact "Riserva di Valore").

**Tutte le decisioni di design sono chiuse (D1–D29).** Restano solo note tecniche
che si risolvono in implementazione:

1. **Indirizzi BEP20** in `reserve.yaml` da verificare on-chain prima di uso live
   (marcati "verify"). Non usati nella fase simulata (R2–R9).
2. **SOL/TRX in live**: dipende dalla liquidità Binance-Peg su PancakeSwap; da
   misurare a R10 (altrimenti si rimuove/sostituisce TRX).
3. `rebalance()` con vendita: in R6 **solo manuale** (pulsante admin). L'automatico
   a `rebalance_band_pct` è un'aggiunta successiva (rientra in R6 solo se semplice).

**Piano completo e coerente. R2 può partire su approvazione.**

---

## 14. STIMA STEP DI LAVORO

| Step | Contenuto |
|---|---|
| ~~R1~~ | **FATTO** 2026-08-30 — `configs/reserve.yaml`, `ReserveConfig`/`ReserveAssetConfig` in config.py, `schemas/reserve.py` (`ReserveSettings`), `domain/reserve/settings.py` (override runtime), `test_reserve_config.py` (12 test). Report `docs/reports/report_reserve_r1_config.md`. |
| ~~R1b~~ | **FATTO** 2026-08-30 — `backend/scripts/aster_spot_probe.py`, report `docs/reports/report_reserve_r1b_aster_spot_probe.md`. Esito in D15: venue live = PancakeSwap per tutti e 5. |
| ~~R2~~ | **FATTO** 2026-08-30 — `models/reserve.py` (3 modelli) + 5 colonne su `PortfolioState` + `_apply_column_migrations` + `repositories/reserve.py` (`ReserveRepository`, mutatori flush-only) + `test_reserve_persistence.py` (11 test). Report `report_reserve_r2_models.md`. |
| ~~R3~~ | **FATTO** 2026-08-30 — `domain/reserve/executor.py` (sim, `live`=NotImplementedError) + `domain/reserve/service.py` (transfer_in/out, sweep, deploy §8ter greedy, rebalance, valuate, snapshot, get_view, set_frozen; fallback `initial_equity`; commit unico per operazione) + `ReserveView` schema + deploy params in config + `test_reserve_service.py` (16 test). Report `report_reserve_r3_service.md`. |
| ~~R4~~ | **FATTO** 2026-08-30 — `GlobalView` D25 (`tradable_equity`, `total_portfolio_equity`, `reserve_*`, `total_portfolio_pnl_pct`; valore riserva dall'ultimo `ReserveSnapshot`, fallback al costo), fee riserva in `total_fees_usd` (D30), `_risk_guardrail` floor su `tradable_equity`, risk manager (`agent/risk/manager.py`) sizing+floor su `total_equity − reserve_transferred_net_usd`. `test_reserve_globalview.py` (8 test). Report `report_reserve_r4_globalview.md`. |
| R4b | Reset/archivio: `persistence/archive.py` include tabelle riserva + azzera i campi `PortfolioState` |
| R5 | API `/agent/reserve/*` + `ReserveView` schema (incl. `reserve_fees_total_usd`, D30) + registrazione router + i18n (base EN) |
| R6 | Slow tick: valuate + snapshot + **sweep (cash)** + **deploy (batch, §8ter)** + rebalance banda larga + `frozen`/`hard_stop` + notifiche (D23) |
| R6b | Benchmark riserva (riuso `_btc_benchmark`) + `trading_pct` + volatility budget "soft" in `GlobalView` + test |
| R7 | Frontend: pulsante "Bank" full-width, `BankPane` (grafico % / $ + pesi), azioni admin (capacità versamento), sotto-scheda Setup › Bank, notifiche, `agentApi.ts`, GlobalPane |
| R8 | Report + `PROJECT_STRUCTURE.md` + verifica startup/guardrail |
| R9 | Mirror dashboard (`dashboard/src/App.tsx`) |
| R10 | *(futuro)* Esecuzione live riserva su PancakeSwap — fuori scope R2–R9 |

Ogni step: implementa → verifica → documenta → report, con approvazione prima del
successivo (AGENTS.md).

# Report — R10 (scaffold): esecuzione live PancakeSwap, testnet-gated

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R10. Ambito concordato con l'utente:
**solo scaffolding + testnet** — nessun indirizzo mainnet attivato, nessun
materiale chiave toccato, gate hard su BSC testnet.

## COSA È STATO FATTO

1. **`backend/app/domain/reserve/live_backend.py`** (nuovo) —
   `PancakeSwapReserveBackend`: traduce ogni buy/sell della riserva in **uno
   swap PancakeSwap V2** tramite `PancakeSwapProvider`, riusando integralmente i
   guardrail condivisi (riserva gas BNB non disattivabile, approval ERC-20
   esatta sul solo router, submission limitata, reconciliation on-chain).
   - **Gate hard testnet**: `_require_testnet()` solleva `ReserveExecutionError`
     se `settings.bsc_network != "testnet"` **prima** di costruire qualunque
     transazione. Ridondante rispetto al guard di config
     (`execution_mode == "live"` già impone testnet) ma tiene la riserva
     fail-closed se quel guard venisse allentato.
   - Risoluzione indirizzi: da `settings.reserve.assets` (`pancakeswap_address`);
     `"WBNB"` → sentinella nativa `NATIVE_EVM_ASSET`; assente → errore.
     USDC di quote da `settings.spot_quote_token_address`.
   - `GasGuard` valorizzato con il notional come `expected_profit_usd` (la
     riserva compra per detenere, non per flippare: nessun "profitto" per
     trade); la riserva gas resta piena.
   - `Fill` ricostruito: `fee_usd` = fee pool 0.25% + gas reale dalla receipt
     (`gas_used * effective_gas_price * bnb_price`); `quantity` da
     `quote.amount_out_atomic`.
   - Esiti: `SKIPPED`/non-`CONFIRMED` → `ReserveExecutionError`.

2. **`backend/app/domain/reserve/executor.py`** —
   - `ReserveExecutor.__init__` accetta `live_backend: ReserveLiveBackend | None`.
   - I rami `live` di `buy`/`sell` non sollevano più `NotImplementedError`:
     delegano a `_live_leg()` → backend. Senza backend → `ReserveExecutionError`
     ("no on-chain backend configured"), non un crash.
   - Nuovo `Protocol` `ReserveLiveBackend`.

3. **`backend/app/domain/reserve/pricing.py`** —
   - `_live_enabled(settings)`: `True` solo se
     `reserve.execution_mode_inherit` **e** `execution_mode == "live"` **e**
     `bsc_network == "testnet"`.
   - `build_reserve_service`: quando live, costruisce `PancakeSwapReserveBackend`
     (BNB price dalla stessa tabella prezzi già fetchata) e passa
     `live=True, live_backend=...` all'executor. In `dry_run` (default) nulla
     cambia.

4. **`backend/app/domain/reserve/__init__.py`** — esporta
   `PancakeSwapReserveBackend`.

## COSA È STATO VERIFICATO

- `backend/.venv/Scripts/python.exe -m pytest backend/tests/unit/test_reserve_live_backend.py`
  → **7 passed**. Coprono: buy delega al provider e ritorna un `Fill` coerente;
  gate mainnet (`ReserveExecutionError` "testnet"); swap `SKIPPED` → errore;
  `"WBNB"` → sentinella nativa; ramo live executor senza backend → errore;
  ramo live executor con backend → delega; `build_reserve_service` resta
  simulato in `dry_run`.
- `pytest backend/tests -k "reserve or execution"` → **126 passed**, 0 regressioni.
- `pytest backend/tests/unit/test_reserve_{service,slow_tick}.py` → 28 passed.
- `ruff check backend/app/domain/reserve/ + test` → clean.
- `python -c "import backend.app.main"` → OK.

## SCOSTAMENTI DAL PIANO

- `quantity` del `Fill` live usa `quote.amount_out_atomic` (stima pre-swap), non
  l'importo effettivamente ricevuto letto dai log di `Swap`. Sufficiente per lo
  scaffold testnet; il parsing esatto della receipt è un raffinamento per il
  passaggio mainnet.
- Nessuno script CLI dedicato aggiunto: `backend/scripts/pancakeswap_smoke_test.py`
  copre già lo smoke swap testnet end-to-end.

## QUESTIONI APERTE (per il live mainnet — NON in questo scope)

- Verifica on-chain dei 5 indirizzi BEP20 in `configs/reserve.yaml` (ancora
  marcati "verify").
- Misura liquidità pool PancakeSwap per Binance-Peg SOL e TRX; se insufficiente,
  rimuovere/sostituire TRX.
- Rimozione del gate testnet (in `live_backend._require_testnet` + guard config
  `Settings` riga ~917) con opt-in esplicito stile `allow_mainnet`.
- `spot_quote_token_address` (USDC) deve essere configurato per l'ambiente
  testnet.

## STATO DELIVERABLE

- `backend/app/domain/reserve/{live_backend.py (nuovo),executor.py,pricing.py,__init__.py}` — modificati.
- `backend/tests/unit/test_reserve_live_backend.py` — nuovo (7 test).
- Doc: `PROJECT_STRUCTURE.md` (STATO STEP), questo report.
- R10 scaffold completo; live mainnet resta gated e non implementato per scelta.

# Report fix regressione market-data frontend

## 1. COSA È STATO FATTO

- Corretta la regressione per cui la tab Preferiti poteva mostrare prezzi non aggiornati o placeholder mentre la chiamata dedicata ai preferiti era lenta.
- Ridotta la lentezza dei refresh ripetuti market-data con una cache in memoria delle identità asset già risolte dal `MarketDataRegistry`.
- Aggiunto un test di regressione backend per impedire che refresh prezzo ripetuti rieseguano la risoluzione identità CMC/CoinGecko.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- `src/hooks/useFavoriteCoinsData.ts` ora accetta un seed di coin già caricate dal mercato e aggiorna subito i preferiti corrispondenti.
- `src/App.tsx` passa alla tab Preferiti il dataset `coins` già disponibile dalla lista mercato.
- `backend/app/data/market_data/registry.py` mantiene una cache per coppia `(provider, app_id)` delle identità già risolte, evitando risoluzioni ripetute per gli stessi asset.
- `backend/tests/integration/test_market_data_providers.py` copre il caso di due refresh prezzo consecutivi sugli stessi asset.

## 3. COSA È STATO VERIFICATO

- Ispezionati i log backend disponibili: le chiamate lente erano correlate a `market_data.registry` e alla risoluzione CMC/CoinGecko degli ID, non ai loop Step 6.
- Verificato che i loop Step 6 risultano solo avviati nei log e non generano richieste market-data.
- Eseguiti test mirati market-data:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/integration/test_market_data_providers.py::test_registry_caches_identity_resolution_for_repeated_price_refreshes backend/tests/integration/test_market_data_api.py::test_backend_market_data_response_shape`
  - esito: `2 passed`
- Eseguito lint backend mirato:
  - `backend\.venv\Scripts\python.exe -m ruff check backend/app/data/market_data/registry.py backend/tests/integration/test_market_data_providers.py`
  - esito: `All checks passed`
- Eseguito typecheck frontend senza build Vite:
  - `npx tsc --noEmit`
  - esito: completato senza errori

## 4. SCOSTAMENTI DAL PIANO

- Non è stata eseguita una build frontend locale perché il progetto richiede di evitare build locali quando possono caricare `.env` reale.
- Non è stato modificato il provider globale selezionato né la configurazione runtime.

## 5. QUESTIONI APERTE

- La prima risoluzione CMC dopo riavvio può ancora richiedere alcuni secondi se il processo non ha cache calda.
- Un miglioramento successivo può introdurre una cache persistente o un mapping provider-ID versionato per i token più usati, ma non è stato incluso per mantenere il fix stretto sulla regressione.

## 6. STATO DELIVERABLE

Completato e verificato con test mirati.

# Report Step 3 - Astrazione Dati Multi-Provider

## 1. COSA È STATO FATTO

- Creata l'interfaccia astratta `MarketDataProvider` con prezzi, OHLCV, ricerca e market list.
- Creati modelli interni normalizzati per asset, quote prezzo e barre OHLCV.
- Implementato `CMCProvider` come provider primario e default.
- Implementato `CoinGeckoProvider` riadattando gli endpoint già usati dall'app.
- Creato `MarketDataRegistry` come selettore globale CMC/CoinGecko senza fallback automatico.
- Aggiunti rate limiter asincrono, cache TTL e budget crediti CMC con stati `ok`, `warning`, `critical`, `exhausted`.
- Aggiunti endpoint backend normalizzati:
  - `GET /api/v1/market-data/provider`
  - `PUT /api/v1/market-data/provider`
  - `GET /api/v1/market-data/markets`
  - `GET /api/v1/market-data/prices`
  - `GET /api/v1/market-data/search`
  - `GET /api/v1/market-data/ohlcv`
- Reso admin-only il cambio provider; il token admin inserito nella UI resta solo nello stato della sessione.
- Sostituita la chiamata CoinGecko diretta del checker notifiche con il provider selezionato.
- Sostituite le chiamate CoinGecko dirette del frontend con `src/services/marketData.ts`.
- Aggiunto `VITE_API_READ_TOKEN` per l'accesso read-only del frontend.
- Aggiunta la configurazione CMC MCP ufficiale e il relativo stato non sensibile.
- Aggiunte chiavi i18n EN/IT per il dominio market data.
- Aggiornati configurazione, workflow APK, backend README e struttura progetto.
- Non sono stati implementati fallback automatico, provider per funzione o terzo provider.

## 2. COME È STATO FATTO

- I consumer dipendono da `MarketDataProvider`; i provider concreti vengono istanziati solo nel registry.
- Il provider default arriva da `Settings` tramite `market_data.provider: cmc`.
- Il cambio dalla UI sviluppatore usa un endpoint admin e vale per tutto il processo fino al riavvio.
- Cache e rate limiting sono applicati prima della chiamata HTTP. Una cache hit non consuma richieste o crediti locali.
- Gli identificativi applicativi restano slug, mentre `provider_id` conserva l'ID nativo CMC/CoinGecko.
- CMC usa ID map, listings latest, quotes latest v3 e OHLCV historical v2.
- Le richieste OHLCV inviano sempre `time_start` e `time_end` e vengono segmentate in finestre massime di 30 giorni, con deduplicazione dei punti ai confini.
- CoinGecko mantiene simple price, markets, search e OHLC esistenti dietro lo stesso contratto.
- Per CMC è usato un limite conservativo di 120 richieste/minuto: Startup documenta 600/minuto complessive, ma `quotes/latest` v3 documenta 120/minuto.
- La documentazione ufficiale indica per Startup una profondità storica di un mese. La segmentazione evita richieste singole oltre 30 giorni, ma non aggira la profondità temporale concessa dal piano.
- Non vengono sintetizzate candele o volumi mancanti.
- Fonti ufficiali verificate:
  - https://coinmarketcap.com/api/documentation/pro-api-reference/pricing
  - https://coinmarketcap.com/api/documentation/pro-api-reference/cryptocurrency
  - https://coinmarketcap.com/api/documentation/pro-api-reference/agent-hub/cmc-mcp

## 3. COSA È STATO VERIFICATO

- Suite completa backend: `15 passed, 1 skipped`.
- Smoke reale CoinGecko: passato con risposta normalizzata valida.
- Smoke reale CMC: passato nell'ambiente utente con `CMC_API_KEY` esportata nel processo (`1 passed, 9 deselected in 3.71s`).
- Selettore CMC/CoinGecko: verificato che le chiamate vadano al provider attivo.
- Normalizzazione: verificata coerenza dei campi comuni CMC/CoinGecko.
- Risposta CMC quotes v3: verificato il formato array corrente.
- Rate limiter: verificato accodamento oltre soglia.
- Cache crediti: verificato che una richiesta identica non consumi un secondo credito.
- Soglie crediti: verificati warning, critical ed exhausted.
- Endpoint backend: verificati symbol, price, volume e OHLCV normalizzato.
- Segmentazione CMC OHLCV: verificata una richiesta da 75 giorni in tre finestre da massimo 30 giorni, con confini contigui e deduplicazione.
- Frontend/checker: verificata assenza di `api.coingecko.com` fuori dall'adapter/config.
- `ruff check backend/app backend/tests`: passato.
- `compileall backend/app backend/tests`: passato.
- `npx tsc -b`: passato.
- JSON locale EN/IT: parsing passato.
- `npm run lint`: non verde per 11 errori React già presenti in `App.tsx`, hook legacy e `SplashOverlay.tsx`; nessun errore TypeScript Step 3.
- Il build Vite locale non è stato eseguito perché la configurazione attuale può leggere `configs/instance.yaml`; la verifica sicura è stata limitata a TypeScript e CI.

## 4. SCOSTAMENTI DAL PIANO

- Corretto il precedente scostamento: Startup supporta un mese di storico. L'endpoint ufficiale corrente resta `/v2/cryptocurrency/ohlcv/historical`, non `v1`.
- La granularità storica CMC a 5 minuti riguarda quote, non OHLCV completo. Il Volume Profile 5m non può usare quei dati senza una fonte diversa.
- CoinGecko fornisce OHLC ma non volume nello stesso endpoint; è valido per monitoring/alert, non garantisce il Volume Profile 5m.
- Il cambio provider runtime non viene persistito: al riavvio torna il valore configurato in `Settings`.
- La conversione completa dei testi legacy frontend IT verso il sistema i18n non è stata completata; sono state aggiunte le chiavi EN/IT Step 3.
- La chiamata CMC reale è stata eseguita dall'utente esportando la chiave nel processo, senza leggere o stampare `.env`.

## 5. QUESTIONI APERTE

- Scegliere una fonte OHLCV 5m completa per il Volume Profile: CMC espone 5 minuti nelle quote storiche, non nell'OHLCV centralizzato.
- Decidere se il selettore runtime debba essere persistito nello Step 5, mantenendo `Settings` come unico punto di caricamento.
- Completare la migrazione i18n dei testi frontend legacy e impostare inglese come default effettivo dell'intera UI.
- Verificare gli alias slug tra provider per preferiti/alert storici quando CMC e CoinGecko usano identificativi diversi.
- Risolvere il debito lint React esistente prima di rendere `npm run lint` un gate CI.

## 6. STATO DELIVERABLE

**Parziale.**

L'astrazione multi-provider, i due adapter, il selettore globale, il checker, il frontend normalizzato, MCP, rate limiting, cache crediti e i test automatici, incluso lo smoke CMC reale, sono implementati e verificati. Il deliverable non è ancora dichiarato raggiunto perché la traduzione completa del frontend legacy non è conclusa e il Volume Profile 5m richiede una fonte OHLCV adeguata.

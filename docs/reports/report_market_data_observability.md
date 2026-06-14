# Report Osservabilità Market Data

## 1. COSA È STATO FATTO

- Aggiunto logging strutturato persistente in `logs/backend.log`.
- Aggiunta rotazione giornaliera con retention configurabile.
- Aggiunto `X-Request-ID` end-to-end tra app e backend.
- Aggiunti log dettagliati per route, registry, risoluzione identità, cache e chiamate provider.
- Aggiunta diagnostica locale frontend degli ultimi 100 eventi market-data.
- Aggiunto un gate CI che impedisce di pubblicare APK senza URL backend e token Vite obbligatori.
- Resi visibili nell'app gli errori di configurazione market-data precedenti alla rete.

## 2. COME È STATO FATTO

- Il middleware genera o conserva il request ID e lo associa al contesto `structlog`.
- Il client invia lo stesso ID nell'header e registra status, durata ed errore senza token.
- I provider registrano endpoint, conteggi, paginazione, cache, crediti e tempi; non registrano header o valori sensibili.
- I nomi dei parametri provider sono filtrati da una whitelist; chiavi e testo completo delle eccezioni esterne non vengono serializzati.
- Il registry registra quantità richieste/restituite e gli ID non risolti per preferiti e prezzi.
- Ricerca e market list espongono conteggi distinti, permettendo di verificare selettore `50/100/200/400/600`.
- La build Android verifica la presenza delle variabili senza stamparne i valori.

## 3. COSA È STATO VERIFICATO

- Suite backend: `29 passed, 1 skipped`.
- Test anti-leak: i riepiloghi log contengono conteggi ma non valori di parametri non autorizzati.
- `ruff check backend/app backend/tests`: passato.
- `npx tsc -b`: passato.
- Nessun token, header Authorization o chiave provider viene registrato.
- I log reali hanno mostrato richieste alert funzionanti ma nessuna richiesta market-data: la causa era `VITE_API_READ_TOKEN` mancante nell'APK, quindi il client si fermava prima della rete.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno Step successivo avviato.
- La diagnostica è stata introdotta come task correttivo trasversale allo Step 3.

## 5. QUESTIONI APERTE

- Verificare sul dispositivo la nuova APK prodotta con `VITE_API_READ_TOKEN` configurato.

## 6. STATO DELIVERABLE

**Raggiunto.**

Il sistema produce evidenze persistenti e correlate e impedisce nuove release Android prive della configurazione market-data necessaria.

# Report Fix Compatibilità ID Preferiti

## 1. COSA È STATO FATTO

- Corretta la regressione che mostrava solo parte dei preferiti dopo il passaggio da release `1.0.35` a CMC.
- Mantenuti invariati i preferiti salvati nel dispositivo.
- Aggiunto un catalogo di alias tra ID storici CoinGecko e slug CMC.
- Reso l'ID storico dell'app l'identità restituita anche quando il provider attivo è CMC.
- Aggiunta paginazione completa del catalogo CMC oltre le prime 5.000 coin.
- Aggiunti test su recupero mirato e lista mercato.

## 2. COME È STATO FATTO

- La release precedente persisteva ID CoinGecko come `binancecoin`, `ripple` e `avalanche-2`.
- CMC restituisce per le stesse coin gli slug `bnb`, `xrp` e `avalanche`.
- L'adapter traduce gli ID solo al confine della richiesta CMC e ripristina l'ID applicativo nella risposta normalizzata.
- Nessun preferito viene cancellato, migrato o sostituito nel `localStorage`.
- L'endpoint CMC map viene interrogato a blocchi da 5.000 fino all'ultima pagina e ogni pagina resta in cache.

## 3. COSA È STATO VERIFICATO

- Suite backend: `20 passed, 1 skipped`.
- Test multi-ID: tre preferiti legacy con slug CMC divergenti vengono tutti restituiti.
- Test lista mercato: BNB da CMC viene normalizzato con ID applicativo `binancecoin`.
- Test catalogo: verificato recupero di una coin nella seconda pagina CMC (`start=5001`).
- `ruff check backend/app backend/tests`: passato.
- `npx tsc -b`: passato.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno Step successivo avviato.
- È stata corretta una lacuna del formato normalizzato Step 3: lo slug provider non può essere usato direttamente come identità persistente.

## 5. QUESTIONI APERTE

- Estendere il catalogo alias quando viene riscontrata una coin con ID divergente non ancora censito.
- Verificare sul dispositivo la lista completa dopo una nuova build APK.

## 6. STATO DELIVERABLE

**Raggiunto nel codice e nei test automatici.**

La verifica finale richiede l'installazione della nuova APK mantenendo i dati dell'app esistenti.

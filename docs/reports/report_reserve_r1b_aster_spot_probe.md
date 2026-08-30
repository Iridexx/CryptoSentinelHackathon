# Report — R1b: verifica Aster spot per gli asset della Riserva

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md` (scheda "Bank" / Riserva di Valore), step R1b.

## COSA È STATO FATTO

Verificata, in sola lettura, la disponibilità di un mercato **spot** su Aster per i
5 asset della riserva (BTC, ETH, BNB, SOL, TRX), come input per la scelta del venue
di esecuzione in `configs/reserve.yaml`.

Aggiunto lo script diagnostico `backend/scripts/aster_spot_probe.py` (GET pubbliche
non autenticate; nessun ordine, nessun movimento fondi, nessuna chiave).

## COME È STATO FATTO

Lo script interroga più URL candidati di `exchangeInfo` finché uno risponde con una
lista di simboli, sia per lo spot sia per il perp, e incrocia i `baseAsset` con i
5 asset target.

Sorgenti che hanno risposto:
- SPOT: `https://sapi.asterdex.com/api/v1/exchangeInfo` → HTTP 200, **68 coppie**.
- PERP: `https://fapi.asterdex.com/fapi/v3/exchangeInfo` → HTTP 200, 569 coppie
  (è l'host già configurato nell'app, `Settings.aster_base_url`).

## COSA È STATO VERIFICATO

| Asset | Spot Aster | Perp Aster |
|---|---|---|
| BTC | ✅ `BTCUSDT` | ✅ `BTCUSDT` |
| ETH | ✅ `ETHUSDT` | ✅ `ETHUSDT` |
| BNB | ✅ `BNBUSDT` | ✅ `BNBUSDT` |
| SOL | ✅ `SOLUSDT` | ✅ `SOLUSDT` |
| TRX | ❌ assente | ✅ `TRXUSDT` |

Osservazioni:
- Il mercato **spot di Aster è piccolo e a tema memecoin / nuove listing** (68
  coppie: ASTER, GIGGLE, HAJIMI, BANANAS31, coppie `TEST*`, ecc.). BTC/ETH/BNB/SOL
  ci sono ma non è un mercato spot profondo su questi asset.
- **TRX** non ha coppia spot su Aster (né USDT, né USDC, né USD1).
- L'**API spot di Aster non è cablata** nel codice: `venues/aster/client.py` usa solo
  l'host futures `fapi.asterdex.com` (`/fapi/v3/...`). Aggiungere l'esecuzione spot
  su Aster significherebbe un nuovo venue (nuovo host `sapi`, endpoint ordini
  firmati) — e l'auth EIP-712 Aster ha già anomalie note su alcuni endpoint
  (memoria `project_aster_auth_split`).

## SCOSTAMENTI DAL PIANO

Nessuno. R1b era esplorativo; l'esito è registrato come decisione **D15** nel piano.

## QUESTIONI APERTE

- **Venue live**: confermato PancakeSwap come venue primario per tutti e 5 gli asset
  (BTCB, Binance-Peg ETH, WBNB, Binance-Peg SOL, Binance-Peg TRX). Aster spot resta
  un'opzione futura solo per BTC/ETH/BNB/SOL e solo se se ne integra il client.
- **TRX in live**: dipende dalla liquidità della pool Binance-Peg TRX su PancakeSwap.
  Da misurare al passaggio live; se insufficiente, si rimuove TRX o lo si sostituisce.
- **Fase simulata (attuale)**: nessun blocco — il MTM usa i prezzi del market-data
  provider, tutti e 5 gli asset (TRX incluso) sono coperti.

## STATO DELIVERABLE

- `backend/scripts/aster_spot_probe.py` — aggiunto, eseguito con successo.
- Decisione D15 aggiornata in `plans/Plan_Reserve.md`.
- Prossimo step: **R1** (config `reserve.yaml` + `Settings` + `ReserveSettings` +
  validazione + test), su approvazione.

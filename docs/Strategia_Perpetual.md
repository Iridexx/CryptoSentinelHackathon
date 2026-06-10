# Strategia di Trading Perpetual — Agente AI Autonomo (v2)

> **Contesto del documento**
> Strategia di trading sui **contratti perpetual** per un agente AI autonomo su **BNB Smart Chain (BSC)**, tramite **PancakeSwap Perpetuals**.
> L'agente opera in autonomia: costruisce una mappa dei prezzi, individua i livelli operativi, e un modello AI (LLM) decide se e come agire entro regole di rischio rigide.
>
> **Versione 2** — aggiornata dopo revisione di un trader professionista. Il cambiamento principale: la strategia passa da uno *score composito di segnali* a un sistema basato sul **Volume Profile** come mappa dei prezzi, con logica **mean-reversion** (rientro in value dopo eccesso) e una **gerarchia di segnali** invece di pesi percentuali.
>
> **Nota:** la strategia Spot (più semplice) resta invariata come fondamenta. Questo documento riguarda **solo il Perpetual**. Il sistema è diviso in **V1 (fondamenta)** e **V2 (struttura definitiva)**.

---

## 1. Filosofia di fondo

Due principi guidano l'intera strategia.

**Principio 1 — L'AI valuta, non genera il segnale.**
Un motore meccanico individua i livelli e le condizioni; l'LLM interviene come **meta-controller** che valuta qualità, contesto e rischio, e decide l'esecuzione. L'AI non "legge il grafico e compra".

**Principio 2 — Il Volume Profile è la mappa, non un indicatore.**
Il difetto dei bot retail è non sapere *dove* entrare e *perché proprio lì*. Il Volume Profile risponde a questa domanda: indica i livelli di prezzo dove il mercato ha scambiato più volume (dove ha "accettato valore"), e quindi dove ha senso operare. Non dice "compra o vendi" — dice **dove il trade ha senso**.

> **Il punto chiave: il Volume Profile individua il livello. Poi conferma di pressione, filtri di regime e agent decidono se vale la pena eseguire.**

---

## 2. Il Volume Profile (la mappa dei prezzi)

### Come viene costruito (V1)

```
ROLLING VOLUME PROFILE 24h
├── Timeframe operativo: candele 5 minuti
├── Finestra del profilo: 288 candele da 5m (= 24h rolling)
├── Aggiornamento: ad ogni nuova candela 5m
└── Tipo: Volume Profile REALE (volume scambiato per livello di prezzo)
    NON TPO/Market Profile (che misura il tempo, non il volume)
```

Perché volume reale e non TPO: ci interessa **dove è entrato capitale**, non solo dove il prezzo è rimasto più a lungo.

Perché finestra rolling e non sessione giornaliera: il crypto gira 24/7 senza chiusure naturali, quindi una finestra mobile è più adatta di una "sessione" rigida ereditata dai futures tradizionali.

### Livelli operativi (V1)

| Livello | Cosa rappresenta | Uso operativo |
|---|---|---|
| **POC** (Point of Control) | Il prezzo con più volume scambiato | Il livello più importante. Target naturale (magnete), zona di valore accettato |
| **VAH** (Value Area High) | Bordo superiore della Value Area | Sopra di esso si cercano eccessi long → possibili short |
| **VAL** (Value Area Low) | Bordo inferiore della Value Area | Sotto di esso si cercano eccessi short → possibili long |

**Value Area = 68% del volume** (leggermente più selettiva del classico 70%, più coerente con una deviazione standard). Da testare 68% vs 70% — conta la robustezza, non la precisione teorica.

### Livelli aggiuntivi (V2)

- **HVN** (High Volume Node): zone di accettazione, rallentamento del prezzo, target intermedi
- **LVN** (Low Volume Node): zone di passaggio rapido, possibili breakout/accelerazioni, livelli di invalidazione

---

## 3. Strategia di ingresso (V1): rientro in value dopo eccesso

La logica principale **non è breakout**, ma **mean reversion**: il prezzo esce dalla Value Area (eccesso), non viene accettato fuori, e rientra. Si entra sul rientro.

### Setup LONG

```
1. Il prezzo scende sotto VAL di almeno X%
2. Pressione di vendita forte (in V1: price action; in V2: delta negativo)
3. MA il prezzo non continua a scendere con efficienza (non fa nuovi minimi rilevanti)
4. Compare un trigger di rientro (es. candela che chiude sopra il massimo precedente)
5. → ENTRO LONG
6. TP1 = VAL (ritorno nella Value Area)
7. TP2 = POC
```

**Esempio:**
```
VAL = 100.000  |  POC = 101.200
Il prezzo scende a 99.600 (sotto VAL)
La pressione recente è molto negativa
MA il prezzo non fa nuovi minimi rilevanti
Una candela chiude sopra il massimo precedente → trigger
=> LONG
TP1 = 100.000 (VAL)  |  TP2 = 101.200 (POC)
```

### Setup SHORT (speculare)

```
1. Il prezzo sale sopra VAH di almeno X%
2. Pressione di acquisto forte (in V1: price action; in V2: delta positivo)
3. MA il prezzo non continua a salire con efficienza
4. Compare un trigger di rientro
5. → ENTRO SHORT
6. TP1 = VAH
7. TP2 = POC
```

---

## 4. Gerarchia dei segnali (non pesi, ma ruoli)

I segnali non hanno pesi percentuali sullo stesso piano. Hanno **ruoli gerarchici**:

```
1. VOLUME PROFILE  → la MAPPA
   Individua il livello: dove ha senso operare (VAH/VAL/POC)

2. DELTA  → la CONFERMA   [price action in V1, delta reale in V2]
   Dice se la pressione è coerente o inefficiente
   (l'eccesso si sta esaurendo?)

3. TREND / REGIME  → il FILTRO   [calcolato con VWAP, non medie mobili classiche]
   Evita la mean reversion contro un impulso troppo forte
   (non si compra un coltello che cade in un trend violento)

4. FUNDING / OI  → il CONTESTO
   Modulano o bloccano il trade
   (il mercato è sbilanciato? troppi long/short da una parte?)

5. AGENT (LLM)  → l'ESECUZIONE
   Decide size, rischio, e se eseguire
```

Questo risolve il problema del "trend troppo pesante": il trend non è più un peso del 35%, è un **filtro di sicurezza** che impedisce di fare mean reversion contro impulsi forti.

### Il calcolo del trend: VWAP, non medie mobili classiche

> **Modifica importante (da revisione di due trader indipendenti):** il filtro di trend NON si calcola con medie mobili classiche (SMA, EMA, MACD).

Motivo: le medie mobili classiche sono **lagging** (ritardate) per costruzione — sono medie sul prezzo *passato*, quindi descrivono dove il mercato *è stato*, non dove *sta andando*. Un agente che le usa per il trend rischia di **entrare a fine movimento** (quando il trend è ormai evidente ma il grosso è già avvenuto), abbattendo il win rate ed entrando in ritardo rispetto all'ATR del singolo asset.

Si usa invece il **VWAP** (Volume Weighted Average Price): è una media ponderata sul **volume in entrata**, quindi segue il movimento *in costruzione* invece di uno *già costruito*. Più attendibile nel breve-medio.

```
FILTRO TREND/REGIME via VWAP
├── Prezzo sopra / sotto VWAP → bias direzionale "presente" (non ritardato)
├── Pendenza del VWAP → forza del movimento in costruzione
├── Distanza prezzo-VWAP → estensione (evita ingressi tardivi)
└── Finestra VWAP: rolling, coerente con il Volume Profile 24h
```

**Sinergia:** il VWAP è volume-based esattamente come il Volume Profile (volume per livello di prezzo). I due strumenti "parlano la stessa lingua" — il volume — e si integrano in modo naturale, molto più di una media mobile classica sovrapposta. L'ATR resta in uso, ma per misurare volatilità/estensione, non per il trend.

> **Nota:** il VWAP era originariamente previsto in V2. Su indicazione dei revisori è stato **anticipato a V1** per il calcolo del trend, vista la sua importanza per il win rate.

### Il ruolo del Delta

- **V1**: la conferma di inefficienza si basa su **price action** (il prezzo non fa nuovi minimi/massimi rilevanti, candela di rientro), eventualmente affiancata da VWAP, ATR ed EMA slope. **Nessun order flow reale** in V1 — la strategia V1 è onestamente un *"Volume Profile Mean Reversion senza order flow reale"*: testabile e solida, anche se più debole della versione completa.
- **V2**: si aggiunge il **Delta reale** (vedi sotto). L'architettura V1 è già predisposta per accoglierlo come "conferma" nella gerarchia, così l'inserimento in V2 è pulito e non richiede riscrittura.

### Delta reale — predisposizione per V2

Il Delta vero non si può ricavare dalle candele OHLCV: richiede il **trade data con aggressor side**. La fonte corretta è **Binance aggregate trades**, usando gli endpoint **futures** (non spot, perché il delta di spot e perpetual diverge).

```
MODULO DEDICATO (V2): orderflow_delta.py
├── Live:     WebSocket  btcusdt@aggTrade (futures stream)
├── Backtest: REST       /fapi/v1/aggTrades (storico)
├── Classificazione aggressor side:
│     if isBuyerMaker == false → aggressive_buy_volume += quantity
│     else                     → aggressive_sell_volume += quantity
│     delta = aggressive_buy_volume − aggressive_sell_volume
├── Aggregazione su barre 5m → delta_bar
├── cum_delta_5, percentile / z-score del delta
└── Salvataggio delta_bar + cumulative_delta nel dataset

⚠️ Endpoint futures (/fapi) per i perpetual — MAI mischiare con spot (/api).
⚠️ Binance è una fonte ESTERNA allo stack ufficiale (CMC/TWAK/BNB SDK):
   da gestire come dipendenza aggiuntiva, con la sua resilienza.
⚠️ Nota: il delta di Binance Futures è un PROXY dell'order flow
   (l'agente esegue su PancakeSwap, non su Binance) — valido per asset
   molto liquidi e arbitraggiati (BTC/ETH), da valutare sui minori.
```

---

## 5. Il meta-controller (LLM) — poteri limitati

L'LLM riceve la situazione (livelli, conferma, filtri, contesto, stato portafoglio) e decide l'esecuzione. **Ma con poteri deliberatamente limitati**, per sicurezza:

```
L'LLM PUÒ:
├── Segnalare situazioni anomale ("regime irregolare, meglio non operare")
├── Ridurre la size
├── Bloccare un trade
└── Decidere se eseguire o restare fuori

L'LLM NON PUÒ:
├── Aumentare la leva
├── Invertire un trade
├── Cambiare parametri live
└── Generare segnali da zero
```

Questa restrizione è una scelta di sicurezza: un modello probabilistico non deve avere il potere di azioni ad alto rischio. L'LLM è un **filtro di giudizio prudente**, non un trader libero.

---

## 6. Direzione delle operazioni

| Modalità | Comportamento | Quando |
|---|---|---|
| **Solo Long** | Solo posizioni rialziste | Fase rialzista / accumulo |
| **Solo Short** | Solo posizioni ribassiste | Fase ribassista dichiarata |
| **Long e Short** | L'agente sceglie secondo il setup | Mercato neutro |

---

## 7. Gestione della leva

| Parametro | Valore |
|---|---|
| Preset conservativo | 2x |
| Preset medio | 3x |
| Preset aggressivo | 5x |
| Personalizzata | Fino al massimo del DEX |

**Leva dinamica via ATR:** più alta è la volatilità (ATR), più la leva viene ridotta, per allontanare il prezzo di liquidazione.
```
ATR basso  → leva piena (impostata)
ATR medio  → leva ridotta (~30%)
ATR alto   → leva ridotta (~50%)
```

---

## 8. Gestione dell'entrata — una sola entrata in V1

> **Modifica importante rispetto alla v1 del documento:** il DCA 60/40 (doppia entrata mediando il prezzo) è stato **rimosso**.

Motivo: mediare una perdita all'inizio è uno dei modi classici in cui i sistemi muoiono. Il trader pensa "il segnale è ancora valido" mentre il mercato è già cambiato.

```
V1: UNA SOLA ENTRATA
└── Nessuna media al ribasso

EVENTUALE AGGIUNTA (solo se in profitto)
└── Si può aggiungere alla posizione SOLO se è già in profitto
    (piramidare i vincitori, mai mediare i perdenti)
```

---

## 9. Stop loss e target

### Stop loss — "dove l'idea è sbagliata"

Lo stop non risponde a "dove l'exchange mi liquida", ma a **"dove la mia idea di trade è invalidata"**.

Per la mean reversion:
- **Long sotto VAL**: l'idea è "il prezzo non viene accettato più in basso e rientra". L'idea è falsa se il prezzo continua ad accettare sotto VAL / rompe il minimo dell'eccesso.
- **Short sopra VAH**: speculare.

```
V1 (semplice):
├── stop long  = entry − ATR(14) × 1.0
├── stop short = entry + ATR(14) × 1.0
└── VINCOLO DI SICUREZZA: lo stop deve SEMPRE stare prima
    del prezzo di liquidazione (sui perp con leva è obbligatorio)

V2 (strutturale):
├── stop oltre il minimo/massimo dell'eccesso + buffer
├── oppure oltre il LVN successivo
└── oppure chiusura di N barre fuori dalla Value Area senza rientro
```

> **Nota di sintesi sul dibattito liquidazione vs struttura:** lo stop si basa sulla **struttura/ATR/invalidazione** (come da revisione). La liquidazione **non** è il criterio dello stop, ma resta un **limite invalicabile**: lo stop strutturale deve comunque cadere prima della liquidazione. Non "o l'uno o l'altro", ma "stop logico, con la liquidazione come tetto di sicurezza".

### Target

```
TP1 = bordo della Value Area (VAL per i long, VAH per gli short)
TP2 = POC
```
Più trailing stop dinamico e take profit parziale (configurabile, default 100%).

### Stop temporale e cooldown

- **Stop temporale**: i perp pagano funding (~ogni 8h); una posizione che non si muove viene chiusa dopo un tempo definito.
- **Cooldown**: timer dopo la chiusura prima di riaprire sullo stesso asset (default 30 min).

---

## 10. Reattività e velocità di reazione

> **Il drawdown è in gran parte funzione del tempo di reazione. Reazione più rapida → drawdown più piccolo.**

La velocità di reazione è una variabile di rischio. Architettura a **due velocità**:

```
LOOP VELOCE (secondi)
├── Sorveglia le posizioni APERTE
├── Stop loss / trailing in near real-time
├── Rileva inversioni di regime rapide
└── Esegue uscite/inversioni IMMEDIATE

LOOP LENTO (minuti)
├── Costruzione/aggiornamento Volume Profile (ogni 5m)
├── Analisi completa + gerarchia segnali
└── Decisione del meta-controller (nuovi ingressi)
```

Bilanciato con anti-overtrading: cooldown, trigger di conferma, e la separazione tra loop veloce (solo gestione del rischio) e loop lento (nuove decisioni). Si reagisce ai cambiamenti **veri**, filtrando il rumore.

---

## 11. Gestione del rischio (Risk Management)

| Parametro | Default suggerito | Funzione |
|---|---|---|
| Capitale per trade | 6% | Capitale per singola operazione |
| Max posizioni aperte | 3 | Posizioni simultanee |
| Esposizione massima totale | 30% | Tetto all'esposizione complessiva |
| Daily Loss Limit | −8% | Stop giornaliero se superato |
| Drawdown cap massimo | −15% (prudenziale) | Limite di drawdown complessivo |
| Liquidità minima del pool | $50.000 | Sotto la soglia, asset escluso |
| Slippage massimo | 1% | Oltre, trade annullato |
| Correlation check | 0.8 | Evita posizioni troppo correlate |

**Controlli aggiuntivi:** check di liquidità in uscita (poter uscire, non solo entrare), riserva gas dinamica in % del BNB, skip se costo gas > profitto atteso.

---

## 12. Applicabilità: il Volume Profile richiede liquidità

Il Volume Profile è affidabile solo su asset con **volume sufficiente e ben distribuito**. Su token poco liquidi (molti dei 149 eligible) il profilo è "vuoto" e rumoroso, quindi inaffidabile.

```
Token liquidi (BNB, ETH, BTC, major) → Volume Profile pienamente attivo
Token poco liquidi                    → VP inaffidabile
                                        → fallback ad altra logica / esclusione
```

Si collega al filtro di liquidità minima già previsto: il VP si attiva solo sopra una certa soglia di liquidità/volume.

---

## 13. Filosofia di ottimizzazione

> **Obiettivo: massimo profitto con il minimo drawdown.**

La mean reversion su livelli precisi (VAH/VAL/POC) con stop logici e stretti è coerente con questo obiettivo: ingressi selettivi, rischio definito, target chiari. Si privilegia la **consistenza** (curva di equity liscia) rispetto all'aggressività.

---

## 14. Riepilogo: V1 vs V2

### V1 — Fondamenta (obiettivo: sistema solido e testabile)
```
├── Rolling Volume Profile 24h su candele 5m
├── Value Area 68%, livelli POC / VAH / VAL
├── Strategia: rientro in value dopo eccesso (mean reversion)
├── Conferma: price action (il prezzo non fa nuovi estremi + candela di rientro)
├── Trend/regime calcolato con VWAP (non medie mobili classiche) — filtro
├── Funding / OI: come filtri di contesto (gerarchia)
├── Stop: ATR(14) × 1.0 (con vincolo pre-liquidazione)
├── Target: TP1 = bordo value, TP2 = POC
├── Una sola entrata (no DCA in perdita)
├── LLM a poteri limitati (valuta/riduce/blocca, non aumenta/inverte)
├── Doppio loop veloce/lento
└── Solo su token sufficientemente liquidi
```

### V2 — Struttura definitiva (dopo i test)
```
├── Delta reale via modulo orderflow_delta.py
│     (Binance aggTrades FUTURES /fapi, classificazione isBuyerMaker,
│      aggregazione 5m, cum_delta, z-score) — come conferma di pressione
├── HVN / LVN aggiunti alla mappa
├── VWAP multi-finestra / VWAP bands (il VWAP base è già in V1 per il trend)
├── Stop strutturale (dietro LVN / oltre accettazione fuori value)
├── Profili multipli (24h + weekly rolling)
├── Filtro Funding/OI più raffinato
└── Eventuale whale flow / liquidity flow (se si trovano fonti precise)
```

---

## 15. Flusso operativo (V1)

```
1. AGGIORNAMENTO MAPPA (ogni 5m, loop lento)
   Costruisce il Volume Profile 24h → POC, VAH, VAL

2. RILEVAMENTO ECCESSO
   Il prezzo esce dalla Value Area (sotto VAL o sopra VAH) di almeno X%

3. CONFERMA DI INEFFICIENZA (price action in V1)
   L'eccesso si esaurisce? (niente nuovi estremi + candela di rientro)

4. FILTRI
   Trend via VWAP (non contro impulso forte) · Funding/OI (contesto) ·
   liquidità · slippage · correlazione · esposizione · drawdown

5. META-CONTROLLER (LLM)
   Valuta coerenza, rileva anomalie, decide size, può bloccare

6. CALCOLO LEVA
   Impostata, ridotta dinamicamente via ATR

7. ENTRATA (una sola)
   Long sotto VAL / Short sopra VAH, sul trigger di rientro

8. GESTIONE (loop veloce per stop/uscite)
   Stop ATR (pre-liquidazione) · TP1 = bordo value · TP2 = POC ·
   trailing · stop temporale (funding) · monitoraggio reattivo

9. USCITA + COOLDOWN
   Chiusura secondo le regole, poi cooldown prima di riaprire
```

---

*Documento v2 — aggiornato dopo revisione professionale. Tutti i valori numerici sono default proposti e configurabili. Il Volume Profile non genera segnali di acquisto/vendita: individua dove il trade ha senso; conferma, filtri e agent decidono l'esecuzione.*

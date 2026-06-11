# Strategia di Trading Perpetual — Agente AI Autonomo (v3)

> **Contesto del documento**
> Strategia di trading sui **contratti perpetual** per un agente AI autonomo su **BNB Smart Chain (BSC)**, tramite **PancakeSwap Perpetuals**.
> L'agente opera in autonomia: costruisce una mappa dei prezzi, individua i livelli operativi, e un modello AI (LLM) decide se e come agire entro regole di rischio rigide.
>
> **Versione 3** — aggiornata dopo seconda revisione professionale. Modifiche rispetto alla v2:
> - Stop loss: anticipato da V2 a V1 lo stop strutturale (estremo candela pre-segnale + ATR×coeff), con cap di rischio % capitale per trade come guardrail obbligatorio.
> - Take profit: sostituito il TP binario (TP1/TP2 + trailing) con schema a tre livelli 50/25/25 e spostamento stop a breakeven+ dopo TP1.
> - Aggiunto guardrail di rischio per trade (perdita massima a stop colpito ≤ X% del capitale).
> - VWAP confermato come filtro di trend; medie mobili classiche escluse (conferma da revisori indipendenti).
> - Entrata singola confermata (no scaglionamento in V1).
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
├── Aggiornamento: ad ogni nuova candela 5m (mai intra-candela)
└── Tipo: Volume Profile REALE (volume scambiato per livello di prezzo)
    NON TPO/Market Profile (che misura il tempo, non il volume)
```

Perché volume reale e non TPO: ci interessa **dove è entrato capitale**, non solo dove il prezzo è rimasto più a lungo.

Perché finestra rolling e non sessione giornaliera: il crypto gira 24/7 senza chiusure naturali, quindi una finestra mobile è più adatta di una "sessione" rigida ereditata dai futures tradizionali.

Perché ricalcolo a chiusura candela e non intra-candela: decidere a candela chiusa evita l'overtrading su dati incompleti. Il loop lento si attiva alla chiusura della candela 5m, non su ogni tick.

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
6. TP1 = VAL (50% della posizione)
7. TP2 = POC (25% della posizione)
8. TP3 = trailing sul 25% residuo
```

**Esempio:**
```
VAL = 100.000  |  POC = 101.200
Il prezzo scende a 99.600 (sotto VAL)
La pressione recente è molto negativa
MA il prezzo non fa nuovi minimi rilevanti
Una candela chiude sopra il massimo precedente → trigger
=> LONG
TP1 = 100.000 (VAL)   → chiude 50% posizione, sposta stop a breakeven+
TP2 = 101.200 (POC)   → chiude 25% posizione
TP3 = trailing        → sul 25% residuo
```

### Setup SHORT (speculare)

```
1. Il prezzo sale sopra VAH di almeno X%
2. Pressione di acquisto forte (in V1: price action; in V2: delta positivo)
3. MA il prezzo non continua a salire con efficienza
4. Compare un trigger di rientro
5. → ENTRO SHORT
6. TP1 = VAH (50% della posizione)
7. TP2 = POC (25% della posizione)
8. TP3 = trailing sul 25% residuo
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

> **Confermato da revisioni di tre trader indipendenti:** il filtro di trend NON si calcola con medie mobili classiche (SMA, EMA, MACD).

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

> **Nota sul filtro multi-timeframe (V2):** un terzo revisore ha suggerito di affiancare al VWAP 5m un filtro di regime su timeframe superiore (es. bias VWAP su finestra più ampia). Il principio è valido; viene rinviato a V2 per non appesantire l'implementazione V1.

### Il ruolo del Delta

- **V1**: la conferma di inefficienza si basa su **price action** (il prezzo non fa nuovi minimi/massimi rilevanti, candela di rientro), eventualmente affiancata da VWAP e ATR. **Nessun order flow reale** in V1 — la strategia V1 è onestamente un *"Volume Profile Mean Reversion senza order flow reale"*: testabile e solida, anche se più debole della versione completa.
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

> **Nota:** un revisore ha indicato incertezza sulla leva dinamica. La scelta di mantenerla è prudenziale: ridurre la leva in volatilità alta allontana la liquidazione e riduce il drawdown, che è il criterio di scoring della gara. Il comportamento è conservativo per default e configurabile.

---

## 8. Gestione dell'entrata — una sola entrata in V1

> **Confermato in v3:** l'entrata è singola. Il DCA e lo scaglionamento di entrate sono stati valutati e rimandati a V2.

Motivo: mediare una perdita all'inizio è uno dei modi classici in cui i sistemi muoiono. Lo scaglionamento di entrate verso l'invalidamento del segnale, pur più disciplinato del DCA classico, moltiplica gli stati da gestire (size parziali, stop su media ponderata) in modo incompatibile con la deadline V1.

```
V1: UNA SOLA ENTRATA
└── Nessuna media al ribasso

EVENTUALE AGGIUNTA (solo se in profitto)
└── Si può aggiungere alla posizione SOLO se è già in profitto
    (piramidare i vincitori, mai mediare i perdenti)
```

> **V2:** valutare entrate scaglionate con invalidamento esplicito del segnale, dopo backtest che dimostri miglioramento del risk/reward rispetto all'entrata singola.

---

## 9. Stop loss e target

### Stop loss — "dove l'idea è sbagliata"

Lo stop non risponde a "dove l'exchange mi liquida", ma a **"dove la mia idea di trade è invalidata"**.

Per la mean reversion:
- **Long sotto VAL**: l'idea è "il prezzo non viene accettato più in basso e rientra". L'idea è falsa se il prezzo rompe il minimo della candela che ha preceduto il segnale di ingresso.
- **Short sopra VAH**: speculare — stop sopra il massimo della candela pre-segnale.

```
V1 (strutturale, anticipato da V2):
├── stop long  = minimo candela pre-segnale − (ATR(14) × coefficiente)
├── stop short = massimo candela pre-segnale + (ATR(14) × coefficiente)
├── coefficiente ATR: configurabile (default 0.5 — buffer oltre la struttura)
│
├── GUARDRAIL RISCHIO PER TRADE (nuovo in v3):
│   La distanza entry→stop non deve implicare una perdita > MAX_RISK_PER_TRADE_PCT
│   del capitale totale. Se lo stop strutturale è troppo lontano:
│   → riduci la size per restare nel limite, OPPURE
│   → salta il trade (skip se la size risultante è sotto il minimo operativo)
│   Formula: size = (capitale × MAX_RISK_PCT) / (entry − stop) × leva
│
└── VINCOLO DI SICUREZZA ASSOLUTO: lo stop deve SEMPRE stare prima
    del prezzo di liquidazione (sui perp con leva è obbligatorio).
    Stop logico prima, liquidazione come tetto invalicabile — mai il contrario.
```

> **Perché stop strutturale e non solo ATR puro:** lo stop sull'estremo della candela pre-segnale ha un significato logico preciso — il prezzo non deve tornare *dove era prima che il segnale scattasse*. L'ATR aggiunge un buffer per il rumore di mercato. Insieme, descrivono "dove l'idea è sbagliata" in modo più robusto dello stop ATR puro (che era arbitrario rispetto alla struttura).

| Parametro | Default | Configurabile |
|---|---|---|
| `PERP_ATR_STOP_MULTIPLIER` | 0.5 | Sì |
| `RISK_MAX_RISK_PER_TRADE_PCT` | 1.5% | Sì |

### Take Profit — schema a tre livelli (nuovo in v3)

> **Modifica v3:** sostituisce il TP binario precedente (TP1/TP2 + trailing configurabile).

```
TP1 = bordo della Value Area (VAL per long, VAH per short)
      → chiude il 50% della posizione
      → SPOSTA LO STOP A BREAKEVEN+ (entry + piccolo buffer)
      → da questo momento il trade non può più chiudersi in perdita

TP2 = POC
      → chiude il 25% della posizione

TP3 = trailing stop dinamico sul 25% residuo
      → lascia correre i vincitori oltre il POC
      → distanza trailing configurabile
```

**Perché questo schema riduce il drawdown:**
- Il 50% chiuso a TP1 assicura profitto immediato su ogni trade che raggiunge il bordo della value area.
- Il breakeven+ dopo TP1 elimina il rischio di perdere un trade che era già in profitto su metà posizione.
- Il trailing sul residuo 25% cattura movimenti estesi senza rinunciare al profitto già assicurato.

| Percentuale | Target | Azione stop |
|---|---|---|
| 50% | TP1 = bordo value | Sposta stop a breakeven+ |
| 25% | TP2 = POC | Nessuna modifica |
| 25% | Trailing | Segue il prezzo |

### Stop temporale e cooldown

- **Stop temporale**: i perp pagano funding (~ogni 8h); una posizione che non si muove viene chiusa dopo un tempo definito (default configurabile).
- **Cooldown**: timer dopo la chiusura prima di riaprire sullo stesso asset (default 30 min).

---

## 10. Reattività e velocità di reazione

> **Il drawdown è in gran parte funzione del tempo di reazione. Reazione più rapida → drawdown più piccolo.**

La velocità di reazione è una variabile di rischio. Architettura a **due velocità**:

```
LOOP VELOCE (secondi)
├── Sorveglia le posizioni APERTE
├── Stop loss / trailing / breakeven in near real-time
├── Rileva inversioni di regime rapide
└── Esegue uscite IMMEDIATE

LOOP LENTO (a chiusura candela 5m)
├── Costruzione/aggiornamento Volume Profile
├── Analisi completa + gerarchia segnali
└── Decisione del meta-controller (nuovi ingressi)
```

**Principio anti-overtrading:** le nuove decisioni di ingresso avvengono **solo a candela chiusa**, mai intra-candela. Questo filtra il rumore, evita segnali su dati incompleti e riduce il numero di decisioni LLM (costo e latenza). Il loop veloce è esclusivamente per la gestione del rischio sulle posizioni aperte.

---

## 11. Gestione del rischio (Risk Management)

| Parametro | Default suggerito | Funzione |
|---|---|---|
| Capitale per trade (size) | 6% | Capitale allocato per singola operazione |
| **Rischio massimo per trade** | **1.5%** | **Max perdita a stop colpito (% capitale) — nuovo v3** |
| Max posizioni aperte | 3 | Posizioni simultanee |
| Esposizione massima totale | 30% | Tetto all'esposizione complessiva |
| Daily Loss Limit | −8% | Stop giornaliero se superato |
| Drawdown cap massimo | −15% (prudenziale) | Limite di drawdown complessivo |
| Liquidità minima del pool | $50.000 | Sotto la soglia, asset escluso |
| Slippage massimo | 1% | Oltre, trade annullato |
| Correlation check | 0.8 | Evita posizioni troppo correlate |

> **Nota sul rischio per trade:** "6% di capitale per trade" è la *size nominale*. Con leva, una size del 6% può rischiare molto di più se lo stop è lontano. Il cap di 1.5% è la perdita **effettiva massima** a stop colpito — se lo stop strutturale implica di più, la size viene ridotta o il trade saltato. I due parametri operano insieme: la size del 6% è il massimo, il rischio dell'1.5% è il vincolo.

**Controlli aggiuntivi:** check di liquidità in uscita (poter uscire, non solo entrare), riserva gas dinamica in % del BNB, skip se costo gas > profitto atteso, filtro di liquidità minima per attivazione Volume Profile.

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

La mean reversion su livelli precisi (VAH/VAL/POC) con stop strutturali, cap di rischio per trade e TP scaglionato 50/25/25 è costruita attorno a questo obiettivo: ogni trade che raggiunge TP1 non può più chiudersi in perdita, il rischio massimo per trade è esplicito e controllato, e la consistenza (curva di equity liscia) è privilegiata rispetto all'aggressività.

---

## 14. Riepilogo: V1 vs V2

### V1 — Fondamenta (obiettivo: sistema solido e testabile)
```
├── Rolling Volume Profile 24h su candele 5m
├── Ricalcolo a chiusura candela (anti-overtrading)
├── Value Area 68%, livelli POC / VAH / VAL
├── Strategia: rientro in value dopo eccesso (mean reversion)
├── Conferma: price action (nessun nuovo estremo + candela di rientro)
├── Trend/regime: VWAP (non medie mobili classiche) — filtro
├── Funding / OI: filtri di contesto (gerarchia)
├── Stop: strutturale (estremo candela pre-segnale + ATR×coeff)
│         con cap rischio per trade (max 1.5% capitale a stop colpito)
│         con vincolo pre-liquidazione
├── Target: TP1 50% (bordo value) → breakeven+
│           TP2 25% (POC)
│           TP3 25% trailing
├── Una sola entrata (no DCA, no scaglionamento)
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
├── VWAP multi-finestra / filtro regime su timeframe superiore
├── Profili multipli (24h + weekly rolling)
├── Filtro Funding/OI più raffinato
├── Valutazione entrate scaglionate con backtest (su invalidamento esplicito)
└── Eventuale whale flow / liquidity flow (se si trovano fonti precise)
```

---

## 15. Flusso operativo (V1)

```
1. AGGIORNAMENTO MAPPA (a chiusura candela 5m, loop lento)
   Costruisce il Volume Profile 24h → POC, VAH, VAL

2. RILEVAMENTO ECCESSO
   Il prezzo esce dalla Value Area (sotto VAL o sopra VAH) di almeno X%

3. CONFERMA DI INEFFICIENZA (price action in V1)
   L'eccesso si esaurisce? (niente nuovi estremi + candela di rientro)

4. FILTRI
   Trend via VWAP (non contro impulso forte) · Funding/OI (contesto) ·
   liquidità · slippage · correlazione · esposizione · drawdown

5. META-CONTROLLER (LLM)
   Valuta coerenza, rileva anomalie, decide size nel rispetto del cap
   rischio per trade, può bloccare

6. CALCOLO SIZE E LEVA
   Size = min(6% capitale, size da cap rischio 1.5%)
   Leva ridotta dinamicamente via ATR

7. ENTRATA (una sola)
   Long sotto VAL / Short sopra VAH, sul trigger di rientro

8. GESTIONE (loop veloce per stop/uscite)
   Stop strutturale (pre-liquidazione) ·
   TP1 50% → breakeven+ · TP2 25% · TP3 25% trailing ·
   stop temporale (funding) · monitoraggio reattivo

9. USCITA + COOLDOWN
   Chiusura secondo le regole, poi cooldown prima di riaprire
```

---

## 16. Note dalle revisioni professionali (storico modifiche)

| Versione | Modifica principale | Fonte |
|---|---|---|
| v1 | Score composito con RSI al 40% | Baseline interna |
| v2 | Volume Profile come mappa, gerarchia segnali, VWAP per trend, stop ATR, entrata singola | Revisione trader 1 + trader 2 |
| v3 | Stop strutturale (candela pre-segnale + ATR), cap rischio 1.5% per trade, TP 50/25/25 + breakeven+ | Revisione trader 3 |

---

*Documento v3 — aggiornato dopo tre revisioni professionali. Tutti i valori numerici sono default proposti e configurabili (salvo i guardrail di qualificazione hardcoded nel piano). Il Volume Profile non genera segnali di acquisto/vendita: individua dove il trade ha senso; conferma, filtri e agent decidono l'esecuzione.*

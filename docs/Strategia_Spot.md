# Strategia di Trading Spot — Agente AI Autonomo (v2)

> **Contesto del documento**
> Strategia di trading sul mercato **spot** per un agente AI autonomo su **BNB Smart Chain (BSC)**, tramite **PancakeSwap**.
> L'agente opera in autonomia: rileva eventi di mercato, valuta la qualità dell'opportunità con strumenti di struttura e momentum, e un modello AI (LLM) decide l'esecuzione entro regole di rischio definite.
>
> **Versione 2** — aggiornata dopo revisione di un trader professionista. Il cambiamento principale: lo Spot passa da *score + conferma* (basato su RSI) a un motore **momentum + struttura di prezzo**, con l'RSI declassato a semplice filtro e l'introduzione di **VWAP, regime EMA, relative volume** e (in V2) **relative strength**.
>
> **Questa è la strategia SPOT** — le fondamenta del sistema, costruite per prime. È un motore **diverso** da quello Perpetual (documento separato), e deve esserlo: Spot e Perp non sono lo stesso gioco.
>
> Il sistema è diviso in **V1 (fondamenta)** e **V2 (struttura definitiva)**.

---

## 1. Filosofia di fondo

Tre principi guidano la strategia.

**Principio 1 — Due giochi diversi: Spot ≠ Perp.**
- **Perp** = precisione e microstruttura (mean reversion su livelli di Volume Profile)
- **Spot** = trovare i cavalli migliori e cavalcare il momentum

Lo Spot non insegue la precisione del singolo livello, ma la **selezione del miglior candidato** tra molti token e il momentum che lo accompagna.

**Principio 2 — Event-driven, non polling continuo.**
L'agente non monitora 149 token ogni secondo. Si attiva su eventi: espansione di volatilità, volume spike. Riduce rumore, overtrading e costi. Nasce dal contesto del progetto (app di monitoraggio con alert) — gli alert diventano il trigger.

**Principio 3 — L'AI valuta, non genera il segnale.**
Un motore meccanico individua l'opportunità e ne misura la qualità; l'LLM interviene come **meta-controller** che approva, riduce o blocca. L'AI non "legge il grafico e compra".

---

## 2. Il trigger: evento di mercato

L'agente entra in azione su un **evento**, non a caso e non in continuo.

```
TRIGGER (arricchito rispetto alla v1)
├── Espansione di volatilità su una coin monitorata
├── + Volume spike (relative volume elevato — vedi §4)
├── + Conferma di struttura (non solo "si muove", ma "si muove bene")
├── Solo coin nei preferiti con flag AI attiva
└── Parametri configurabili
```

> **Correzione chiave rispetto alla v1:** il solo trigger di volatilità è pericoloso — rischia di far comprare il **pump quando è già finito** (si entra sulla candela finale, mentre chi era dentro prima vende). Per questo il trigger non è più solo "volatilità anomala", ma **volatilità + volume spike + qualità di struttura**, per distinguere l'**inizio** di un movimento dalla sua **fine**.

---

## 3. Il motore del segnale: regime + struttura + momentum

Quando il trigger scatta, l'agente non calcola un semplice "score di indicatori", ma valuta l'opportunità attraverso una sequenza logica.

### Pesi ribilanciati

| Componente | Peso v1 (vecchio) | Peso v2 (nuovo) | Ruolo |
|---|---|---|---|
| **Trend / struttura** | — | **30%** | Regime e qualità della struttura di prezzo |
| **Volume relativo** | 35% (24h assoluto) | **30%** | Volume attuale vs media recente |
| **BTC context** | 15% | **15%** | Contesto di mercato (rotazione BTC/alt) |
| **RSI** | 40% | **15%** | Declassato a filtro, non più cuore |
| **Sentiment (Fear & Greed)** | 10% | **10%** | Solo filtro macro leggero |

> **La correzione più importante:** l'RSI scende da 40% a 15%. Motivo: l'RSI misura *quanto velocemente* ci si è mossi, non il *valore*. Una coin a +100% può restare RSI 80 per giorni (e un bot RSI-centrico la venderebbe troppo presto); una coin "morta" crollata può avere RSI 20 (e verrebbe comprata a torto). L'RSI resta utile come filtro, non come motore.

### Dettaglio delle componenti

**Trend / struttura (30%)**
Il regime in cui si trova la coin. Il riferimento **primario** è il **VWAP** (volume-based, "presente"), affiancato dalla struttura di prezzo:
- **VWAP** → riferimento primario del trend: prezzo sopra/sotto VWAP (bias), pendenza del VWAP (forza del movimento in costruzione). Preferito alle medie mobili classiche perché non è ritardato (vedi nota sotto).
- **Market structure** → higher high / higher low, breakout di livelli precedenti
- **EMA 20/50** → uso secondario/di conferma per inquadrare la fase (trend/accumulazione/downtrend), NON come riferimento primario
La domanda di fondo: *"in che fase è questa coin?"* — non si compra un pump già esteso né un coltello che cade.

> **Nota (da revisione di due trader indipendenti):** le medie mobili classiche (SMA/EMA/MACD) sono **ritardate** per costruzione — descrivono il passato, non il movimento in costruzione. Usarle come riferimento primario del trend porta a entrare a fine movimento, abbattendo il win rate. Per questo il **VWAP è il riferimento primario** del trend (volume-based, più attendibile nel breve-medio), e le EMA restano solo come supporto secondario per inquadrare la fase. Il VWAP è già usato anche come filtro anti-pump nella sezione 4 — qui assume anche il ruolo di riferimento di trend, in piena coerenza con l'impianto volume-based.

**Volume relativo (30%)**
Non il volume 24h assoluto, ma il **relative volume**: il volume attuale rispetto alla media recente.
```
Esempio: volume candela 15m = 5× la media delle ultime 100 candele → interessante
```
Misura se *adesso* sta succedendo qualcosa di anomalo, non se la coin ha tanto volume in generale.

**BTC context (15%)**
Contesto, non trigger. BTC dominante → spesso le alt soffrono. Dominance in calo → possibile rotazione verso le alt.

**RSI (15%)**
Filtro di supporto. RSI 15min + 1h come conferma (in V2 si aggiunge il 4h per il trend). Utile per evitare estremi, non per decidere l'ingresso.

**Sentiment / Fear & Greed (10%)**
Solo filtro macro. Cambia su scala giornaliera, troppo lento per i segnali brevi del bot. Non guida le decisioni, le contestualizza.

---

## 4. Entry quality: il "DOVE" (VWAP + struttura)

> **Correzione chiave:** mancava la risposta a *"a quale prezzo entro?"*. Un punteggio alto non basta — bisogna sapere **dove** l'ingresso è favorevole. Per lo Spot non serve il Volume Profile (troppo pesante e poco affidabile su 149 token): bastano **VWAP + market structure**, più robusti.

### VWAP — il filtro anti-pump (centrale)

Il **VWAP** (prezzo medio ponderato per volume) evita di comprare troppo sopra il prezzo medio:

```
Regola: NO long se prezzo > VWAP + (X × ATR)
```
Cioè: non si insegue una coin già troppo estesa sopra il suo prezzo medio. È la protezione principale contro il "comprare la candela finale".

### Market structure

- Ingresso favorito su **breakout + retest** di un livello, non sull'estensione
- Distanza dai massimi/minimi recenti
- Candle exhaustion (segnali di esaurimento del movimento) — pieno in V2

### Estensione ATR

L'ATR misura quanto la coin è "tirata": un movimento troppo esteso oltre N×ATR dal VWAP è un segnale di ingresso tardivo → si evita o si riduce.

---

## 5. Il meta-controller (LLM) — poteri limitati

L'LLM riceve regime, qualità d'ingresso e contesto, e decide:
- Approva l'ingresso
- Riduce la size (opportunità valida ma contesto incerto)
- Blocca (situazione anomala)

Come sui Perp, poteri **deliberatamente limitati**: l'LLM valuta, riduce, blocca — **non** genera segnali da zero né stravolge i parametri. Produce una motivazione testuale registrata per trasparenza.

---

## 6. Gestione dell'entrata — niente media in perdita

> **Correzione (coerente con i Perp):** il DCA 60/40 con media al ribasso è stato rimosso.

```
V1: PRIMA ENTRATA
└── Una entrata sull'opportunità validata

EVENTUALE AGGIUNTA — solo a favore
└── Si aggiunge SOLO se:
    - la posizione è già in profitto, E
    - c'è conferma (breakout confermato / nuovo massimo)
└── MAI aggiungere perché "scende ma credo ancora nel segnale"
```

Piramidare i vincitori, mai mediare i perdenti.

---

## 7. Gestione della posizione e uscite

### Stop Loss — ATR da subito

> **Correzione:** niente stop fisso in %. Si usa **ATR fin dalla V1**.

Motivo: BNB e una microcap hanno volatilità completamente diverse; uno stop fisso al 5% è troppo largo per una e troppo stretto per l'altra. Lo stop ATR si adatta automaticamente alla volatilità dell'asset.
```
stop = entry − (ATR(14) × moltiplicatore)   [moltiplicatore configurabile]
```

### Take Profit — parziale + trailing

> Combinazione consigliata dal revisore:
```
TP parziale → chiude una parte della posizione a un primo obiettivo
Trailing stop → segue il prezzo sul resto, lascia correre i vincitori
```
(Take profit parziale configurabile; default impostabile.)

### Stop temporale e cooldown
- **Stop temporale**: chiusura se la posizione non si muove entro N ore (default 4–6h).
- **Cooldown**: timer dopo la chiusura prima di riaprire sulla stessa coin (default 30 min).

---

## 8. Reattività e velocità di reazione

> **Il drawdown è in gran parte funzione del tempo di reazione. Reazione più rapida → drawdown più piccolo.**

Architettura a **due velocità**:
```
LOOP VELOCE (secondi) → posizioni aperte, stop, trailing, uscite immediate
LOOP LENTO (minuti)   → scansione, regime, entry quality, decisione LLM
```
Bilanciato con anti-overtrading (cooldown, conferme di struttura).

---

## 9. Gestione del rischio (Risk Management)

| Parametro | Default suggerito | Funzione |
|---|---|---|
| Capitale per trade | 6% | Capitale per singola operazione |
| Max posizioni aperte | 3 | Posizioni simultanee |
| Esposizione massima totale | 30% | Tetto all'esposizione |
| Daily Loss Limit | −8% | Stop giornaliero |
| Drawdown cap massimo | −15% (prudenziale) | Limite di drawdown complessivo |
| Liquidità minima del pool | $50.000 | Sotto la soglia, coin esclusa |
| Slippage massimo | 1% | Oltre, trade annullato |
| Stop loss | ATR(14) × moltiplicatore | Adattivo alla volatilità |
| Take profit | Parziale + trailing | — |
| Correlation check | 0.8 | Evita posizioni correlate |
| Cooldown timer | 30 min | Attesa prima di riaprire |

**Controlli aggiuntivi:** check di liquidità in uscita, riserva gas dinamica in % del BNB, skip se gas stimato > profitto atteso.

---

## 10. Filosofia di ottimizzazione

> **Obiettivo: massimo profitto con il minimo drawdown.**

Lo Spot punta a **selezionare i candidati migliori** (non quelli che salgono a caso, ma quelli con struttura e volume di qualità) ed entrare a **prezzi favorevoli** (filtro VWAP), con stop adattivi (ATR). Consistenza sopra aggressività.

---

## 11. Applicabilità sui 149 token

Lo Spot opera sulla lista eligible (149 BEP-20). A differenza del Volume Profile (che richiede molta liquidità), VWAP + market structure + relative volume sono **più robusti anche su token meno liquidi**. Resta comunque attivo il filtro di liquidità minima per escludere i pool troppo sottili.

---

## 12. Il nuovo motore Spot (schema)

```
TOKEN SCANNER (coin preferite + flag AI)
        ↓
LIQUIDITY FILTER (esclude pool troppo sottili)
        ↓
EVENTO: volume spike / volatility expansion
        ↓
REGIME: trend positivo? accumulazione?   (VWAP primario + EMA 20/50 di supporto)
        ↓
ENTRY QUALITY: distanza da VWAP · supporto/resistenza · breakout/retest · estensione ATR
        ↓
AGENT (LLM): approva / riduce / blocca
        ↓
ENTRATA → gestione (ATR stop · TP parziale + trailing · loop veloce) → uscita + cooldown
```

---

## 13. Riepilogo: V1 vs V2

### V1 — Fondamenta (essenziale, fattibile per la deadline)
```
├── Trigger arricchito: volatilità + volume spike
├── Pesi ribilanciati (RSI declassato a 15%)
├── Relative volume (al posto del volume 24h assoluto)
├── Regime: VWAP primario + EMA 20/50 di supporto (trend / accumulazione / downtrend)
├── VWAP come filtro anti-pump (no long se prezzo > VWAP + X·ATR)
├── ATR per stop loss (adattivo) e per misurare l'estensione
├── Entrata singola (no media in perdita; aggiunta solo a favore)
├── Take profit parziale + trailing sul resto
├── LLM a poteri limitati (approva / riduce / blocca)
├── Doppio loop veloce/lento
└── Tutti i controlli di rischio
```

### V2 — Struttura definitiva (dopo i test)
```
├── RELATIVE STRENGTH: ranking dei token per sovraperformance relativa
│     → "non voglio quello che sale, voglio quello che sovraperforma gli altri"
│     (rinviato a V2: richiede confronto in tempo reale tra molti token,
│      tempo e risorse non disponibili per la V1)
├── Market structure completa (breakout/retest rilevati automaticamente)
├── Candle exhaustion detection (riconoscere la fine di un movimento)
├── RSI multi-timeframe esteso (aggiunta del 4h per il trend)
└── Raffinamenti dei filtri di contesto (BTC dominance, sentiment)
```

---

## 14. Flusso operativo (V1)

```
1. TRIGGER
   Volume spike + espansione di volatilità su una coin (preferiti + flag AI)

2. LIQUIDITY FILTER
   Esclude i pool sotto la soglia minima

3. REGIME (VWAP primario + EMA 20/50 di supporto)
   La coin è in trend positivo / accumulazione? (evita downtrend e pump esteso)

4. ENTRY QUALITY
   Distanza da VWAP (no long se troppo esteso) ·
   struttura (breakout/retest) · estensione ATR

5. MOTORE SEGNALE
   Trend/struttura 30% + Volume relativo 30% + BTC context 15% +
   RSI 15% (filtro) + Sentiment 10% (filtro macro)

6. META-CONTROLLER (LLM)
   Approva / riduce size / blocca · motivazione registrata

7. CONTROLLI DI RISCHIO
   Liquidità · slippage · check uscita · esposizione ·
   correlazione · drawdown · daily loss · riserva gas

8. ENTRATA (una sola)
   Aggiunta solo se in profitto + breakout confermato

9. GESTIONE (loop veloce)
   Stop ATR · take profit parziale + trailing · stop temporale

10. USCITA + COOLDOWN
```

---

## 15. Note dalla revisione professionale (sintesi delle modifiche)

Modifiche applicate rispetto alla prima versione dello Spot:
1. **RSI** da 40% (cuore) → 15% (filtro)
2. **Volume**: da 24h assoluto → **relative volume**
3. **Aggiunto regime** con VWAP primario + EMA 20/50 di supporto (trend/structure 30%)
4. **Aggiunto VWAP** come filtro anti-pump (centrale)
5. **Aggiunta estensione ATR** per evitare ingressi tardivi
6. **Trigger arricchito**: non solo volatilità, ma volatilità + volume spike + struttura (anti-pump)
7. **Stop**: da fisso % → **ATR da subito**
8. **DCA**: rimossa la media in perdita → aggiunta solo a favore
9. **Fear & Greed**: da componente → filtro macro leggero
10. **Relative strength** introdotto come obiettivo (rinviato a V2)

Distinzione finale tra i due motori:
- **Perp** = precisione e microstruttura
- **Spot** = trovare i cavalli migliori e cavalcare il momentum

---

*Documento v2 — aggiornato dopo revisione professionale. Tutti i valori numerici sono default proposti e configurabili. La strategia Spot è la "fondamenta" del sistema; la strategia Perpetual (documento separato) è un motore distinto e complementare.*

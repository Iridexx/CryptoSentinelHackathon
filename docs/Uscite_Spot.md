# Strategia di Uscita — SPOT

> Come l'agente chiude le posizioni **spot** in profitto e in perdita.
> Riferimento codice: `backend/app/agent/service.py` (chiusure) e
> `backend/app/agent/signals/spot/momentum.py` (livelli).
> Parametri attivi: `configs/strategy_spot.yaml`.

Lo spot è **solo LONG** (si compra e si rivende). Quindi si guadagna se il
prezzo sale e si perde se scende.

---

## 1. I livelli vengono fissati all'apertura

Quando l'agente apre la posizione al prezzo di entrata, calcola subito 4 livelli:

| Livello | Formula | Valore tipico | A cosa serve |
|---|---|---|---|
| **Stop Loss (SL)** | il più lontano tra `entrata − ATR×1.5` e `entrata − 1%` | almeno −1% sotto | uscita in **perdita** |
| **Take Profit 1 (TP1)** | `entrata + 3%` | +3% | primo incasso (**parziale**) |
| **Take Profit 2 (TP2)** | `entrata + 6%` | +6% | incasso finale |
| **Trailing stop** | segue il prezzo a `−2%` dal massimo | dinamico | protegge il profitto |

> Lo SL non è mai più stretto dell'1%: se la volatilità (ATR) è bassissima,
> usa comunque almeno −1% per non farsi buttare fuori dal rumore.

---

## 2. Ordine di controllo delle uscite (vince il primo che scatta)

Ad ogni aggiornamento di prezzo l'agente controlla, **in quest'ordine**:

1. **Stop Loss** → prezzo ≤ SL
2. **Take Profit 2** → prezzo ≥ TP2 *(solo se TP1 è già stato preso)*
3. **Take Profit 1** → prezzo ≥ TP1 *(solo la prima volta)*
4. **Trailing stop** → prezzo ritraccia sotto il livello trascinato *(solo dopo TP1)*
5. **Stop temporale** → posizione aperta da troppo tempo

---

## 3. Uscita in PROFITTO

### Passo 1 — TP1 a +3% → incasso parziale (50%)
- Quando il prezzo tocca **+3%**, l'agente vende **metà posizione** e mette in
  cassa il profitto su quella metà.
- La posizione resta aperta con il **50% residuo** e si marca `tp1_reached`.
- Da questo momento si attiva il **trailing stop**.

### Passo 2 — gestione del residuo
Il restante 50% può chiudersi in tre modi (in profitto):

- **TP2 a +6%** → vende tutto il residuo: massimo guadagno.
- **Trailing stop** → se dopo TP1 il prezzo sale e poi ritraccia del **2%** dal
  massimo raggiunto, chiude il residuo bloccando comunque un buon profitto.
- *(Stop temporale, vedi sotto — può chiudere anche in leggero profitto.)*

> **Logica:** si "mette al sicuro" subito metà del guadagno a +3%, poi si lascia
> correre l'altra metà puntando a +6%, ma protetti dal trailing che sale insieme
> al prezzo e non scende mai.

---

## 4. Uscita in PERDITA

- **Stop Loss** → se il prezzo scende fino allo SL (almeno −1%, più ampio se
  l'ATR è alto), chiude **tutta** la posizione e registra la perdita.
- Lo SL ha **priorità massima**: viene controllato per primo, prima di ogni TP.
- Non c'è media in perdita: l'agente non aggiunge mai size a una posizione in rosso.

---

## 5. Stop temporale (uscita "neutra")

- Se la posizione resta aperta **oltre 6 ore** senza aver toccato né SL né TP,
  l'agente la chiude comunque (`time_stop`).
- Serve a liberare capitale da trade "morti" che non si muovono.
- Il risultato può essere un piccolo profitto o una piccola perdita, a seconda
  di dov'è il prezzo in quel momento.

---

## 6. Riepilogo motivi di chiusura

| Motivo (`close_reason`) | Quando | Esito | Quota chiusa |
|---|---|---|---|
| `take_profit_1` | prezzo ≥ +3% | profitto | 50% (parziale) |
| `take_profit_2` | prezzo ≥ +6% (dopo TP1) | profitto | residuo (100%) |
| `trailing_stop` | ritraccia −2% dal max (dopo TP1) | profitto | residuo (100%) |
| `stop_loss` | prezzo ≤ SL | perdita | 100% |
| `time_stop` | aperta da > 6 ore | neutro | 100% |

---

## 7. In una frase

> **Profitto:** incassa metà a +3%, lascia correre il resto verso +6% protetto da
> un trailing al −2%.
> **Perdita:** taglia subito allo stop loss (almeno −1%), senza mai mediare.
> **Tempo:** dopo 6 ore chiude comunque le posizioni ferme.

---

### Parametri (modificabili in `configs/strategy_spot.yaml`)

| Parametro | Valore attuale |
|---|---|
| `partial_take_profit_pct` | 3.0 (→ TP1 +3%, TP2 +6%) |
| `atr_stop_multiplier` | 1.5 |
| distanza minima SL | 1.0% |
| `trailing_distance_pct` | 2.0 |
| `time_stop_hours` | 6 |

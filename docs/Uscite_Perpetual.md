# Strategia di Uscita — PERPETUAL (PERP)

> Come l'agente chiude le posizioni **perp** in profitto e in perdita.
> Riferimento codice: `backend/app/agent/service.py` (chiusure) e
> `backend/app/agent/signals/perp/volume_profile.py` (livelli).
> Parametri attivi: `configs/strategy_perp.yaml`.

Il perp è **LONG e SHORT** con **leva** (default ×2, dinamica fino a ×5).
- **LONG:** si guadagna se il prezzo sale, si perde se scende.
- **SHORT:** si guadagna se il prezzo scende, si perde se sale.

I livelli si basano sul **Volume Profile**: POC (prezzo più scambiato), VAH
(bordo alto dell'area di valore) e VAL (bordo basso).

---

## 1. I livelli vengono fissati all'apertura

| Livello | LONG | SHORT | A cosa serve |
|---|---|---|---|
| **Stop Loss (SL)** | `minimo candela prec. − ATR×1.0` | `massimo candela prec. + ATR×1.0` | uscita in **perdita** |
| **Take Profit 1 (TP1)** | `VAL` | `VAH` | primo incasso (**parziale**) |
| **Take Profit 2 (TP2)** | `POC` | `POC` | incasso finale |
| **Trailing stop** | segue a `−1%` dal massimo | segue a `+1%` dal minimo | protegge il profitto |
| **Liquidazione** | `entrata × (1 − 1/leva)` | `entrata × (1 + 1/leva)` | livello da evitare |

> Lo SL è messo "dove l'idea è sbagliata": appena oltre l'estremo della candela
> che ha generato il segnale, con un cuscinetto pari all'ATR.

---

## 2. Ordine di controllo delle uscite (vince il primo che scatta)

Ad ogni aggiornamento di prezzo l'agente controlla, **in quest'ordine**:

1. **Stop Loss** → LONG: prezzo ≤ SL · SHORT: prezzo ≥ SL
2. **Take Profit 2** → LONG: prezzo ≥ POC · SHORT: prezzo ≤ POC *(solo dopo TP1)*
3. **Take Profit 1** → LONG: prezzo ≥ VAL · SHORT: prezzo ≤ VAH *(solo la prima volta)*
4. **Trailing stop** → ritraccia oltre il livello trascinato *(solo dopo TP1)*
5. **Stop temporale** → posizione aperta da troppo tempo

---

## 3. Uscita in PROFITTO

### Passo 1 — TP1 → incasso parziale (50%)
- Quando il prezzo raggiunge **TP1** (VAL per il long, VAH per lo short),
  l'agente chiude **metà posizione** e incassa il profitto su quella metà.
- Resta aperto il **50% residuo**, si marca `tp1_reached` e si attiva il **trailing**.

### Passo 2 — gestione del residuo
Il restante 50% può chiudersi in profitto in tre modi:

- **TP2 = POC** → chiude tutto il residuo al "centro di gravità" dei prezzi.
- **Trailing stop (1%)** → dopo TP1, se il prezzo va a favore e poi ritraccia
  dell'**1%** dal punto migliore, chiude il residuo bloccando il profitto.
- *(Stop temporale, vedi sotto.)*

> **Logica:** identica allo spot ma con distanze più strette (trailing 1%) perché
> la leva amplifica i movimenti: si incassa metà a TP1, si lascia correre il
> resto verso il POC protetti da un trailing aggressivo.

---

## 4. Uscita in PERDITA

- **Stop Loss** → se il prezzo va contro fino allo SL, chiude **tutta** la
  posizione e registra la perdita. Ha **priorità massima**.
  - LONG: prezzo scende a `min candela − ATR`
  - SHORT: prezzo sale a `max candela + ATR`
- **Liquidazione** → è il livello dove la leva azzererebbe il margine
  (`entrata × (1 ∓ 1/leva)`). Lo SL è **sempre più vicino** della liquidazione,
  quindi in condizioni normali si esce allo stop **prima** di arrivare lì.
- Nessuna media in perdita: l'agente non aggiunge mai size a una posizione in rosso.

---

## 5. Stop temporale (uscita "neutra")

- Se la posizione resta aperta **oltre 8 ore** senza toccare SL né TP, l'agente
  la chiude comunque (`time_stop`).
- Evita di tenere esposizione con leva su trade fermi (costo di funding e rischio).
- Il risultato può essere un piccolo profitto o una piccola perdita.

---

## 6. Riepilogo motivi di chiusura

| Motivo (`close_reason`) | Quando (LONG / SHORT) | Esito | Quota chiusa |
|---|---|---|---|
| `take_profit_1` | prezzo ≥ VAL / ≤ VAH | profitto | 50% (parziale) |
| `take_profit_2` | prezzo ≥ POC / ≤ POC (dopo TP1) | profitto | residuo (100%) |
| `trailing_stop` | ritraccia 1% dal punto migliore (dopo TP1) | profitto | residuo (100%) |
| `stop_loss` | prezzo oltre lo SL | perdita | 100% |
| `time_stop` | aperta da > 8 ore | neutro | 100% |

---

## 7. In una frase

> **Profitto:** incassa metà al primo bordo dell'area di valore (VAL/VAH), lascia
> correre il resto verso il POC protetto da un trailing all'1%.
> **Perdita:** taglia allo stop loss appena oltre la candela del segnale, ben
> prima della liquidazione, senza mai mediare.
> **Tempo:** dopo 8 ore chiude comunque le posizioni ferme.

---

### Parametri (modificabili in `configs/strategy_perp.yaml`)

| Parametro | Valore attuale |
|---|---|
| `value_area_pct` | 68.0 (definisce VAH/VAL attorno al POC) |
| `atr_stop_multiplier` | 1.0 |
| distanza trailing | 1.0% (`PERP_TRAILING_DISTANCE_PCT`) |
| `time_stop_hours` | 8 |
| `default_leverage` / `max_leverage` | 2 / 5 |

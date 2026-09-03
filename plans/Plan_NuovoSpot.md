# Piano — Nuovo motore SPOT

Stato: **BOZZA IN DISCUSSIONE** — non iniziare l'implementazione senza approvazione esplicita (AGENTS.md §Required Documentation).

Ultimo aggiornamento: 2026-09-02 (6ª revisione: §5.8 analisi d'integrazione con la
struttura attuale — 3 blocchi trovati (brain che scarta tutto, tetto di esposizione,
token senza prezzo) risolti in una nuova fase F0b; interruttore di regime asimmetrico
EMA20/EMA50 che non liquida piu' (S18), quindi N4 superato)

Revisione precedente: 2026-09-02 (5ª revisione: §4.8 nodi operativi N10-N16 tutti
decisi; eliminato lo scarico parziale (S11); spot vecchio spento via markets_enabled)

Revisione precedente: 2026-08-31 (4ª revisione: passata di verifica finale —
riferimenti di codice passati dai numeri di riga ai nomi dei simboli, incoerenze fra
sezioni sanate, §5.7 sullo stato della suite di test, fase F0)

Revisioni precedenti: 3ª — nodi logici §4.7 (ingresso e uscita si annullavano a
vicenda, la scala poteva restare incompiuta per sempre), isteresi di regime, guardia
sulla divergenza di prezzo Binance/pool, migrazione posizioni vecchie. 2ª — verifica
sul codice reale: la scala diventa *add su posizione* e non nuovi ingressi.

---

## 1. OBIETTIVO

Sostituire l'attuale motore spot (momentum su breakout a 5 minuti) con un motore
**forza relativa + ingresso su ritracciamento**, progettato per un **bull market**
e spento in bear.

Frase guida: **si sceglie CHI comprare per forza, si sceglie QUANDO comprarlo per
debolezza temporanea.**

### Perché il modello attuale non funziona

| Difetto | Conseguenza |
|---|---|
| Segnale su candele 5m (breakout + volume + volatilità) | Cattura micro-spike che rientrano subito: si compra il massimo della candela |
| Nessuna selezione cross-sezionale | Si compra qualunque coin passi il gate assoluto, anche la più debole del gruppo |
| Ingresso singolo per asset | Nessuna mediazione del prezzo, il costo d'ingresso è quello del primo trigger |
| TP1 a 2,5 ATR chiude il 60% | Vincite tagliate presto; il 40% residuo punta a 4,5 ATR e spesso rientra |
| 25% del quality score è costante (`btc_context` e `sentiment` a 0.5) | Un quarto del punteggio non discrimina nulla |
| Regime valutato su BTC 15m | Troppo rapido e rumoroso; non rileva un bear delle alt con BTC fermo |

### Premessa di regime (decisa dall'utente)

Si sta andando **verso un bull market**. Il motore spot è progettato per quella
condizione. **In bear il motore spot non si attiva proprio**: l'interruttore
generale non è un filtro da calibrare, è un on/off dell'intero motore.

---

## 2. DECISIONI CONFERMATE

| # | Tema | Decisione |
|---|---|---|
| S1 | Selezione asset | **Forza relativa contro BTC su 30 giorni**, cross-sezionale sull'universo. Non un gate assoluto per asset. |
| S2 | Timing d'ingresso | **Ritracciamento dentro la salita**, non capitolazione. L'asset deve restare sopra la propria media 50g. |
| S3 | Ingressi per asset | **Sempre 2-3 tranche a size decrescente** (50/30/20). Mai ingresso singolo. Distanze in ATR, non in % fissa. |
| S4 | Stop loss di prezzo | **Nessuno.** Le uscite sono strutturali (rottura trend, perdita forza relativa, regime). |
| S5 | Interruttore generale | **Asimmetrico**: accende con BTC sopra la **EMA 20 daily**, spegne solo sotto la **EMA 50 daily**. Piu' la salute delle alt (45% accende / 35% spegne). |
| S19 | Capitale | **Budget separati per mercato**: 40% spot / 60% perp dell'equity tradabile (configurabile). Ogni motore dimensiona sulla **propria fetta**, non sul totale: cosi' non si affamano a vicenda e la somma non puo' superare il 100%. |
| S20 | Dimensionamento | **Adattivo al capitale**: numero di posizioni e di tranche derivati da quanto capitale c'e', imponendo che ogni tranche superi una soglia economica (`min_tranche_usd`). Crescendo il conto si arriva da soli alla configurazione piena, senza rimettere le mani nei parametri. |
| S18 | Cosa fa il regime | **Blocca solo gli acquisti, non liquida.** Spento = niente ingressi e niente tranche; le posizioni aperte restano gestite dalle uscite per asset. Senza questo, una media veloce svuoterebbe il portafoglio a ogni incrocio. |
| S6 | Timeframe | **Daily** (chiusure) per regime, classifica e tutte le medie: BTC 100g, asset 50g, uscita 20g. **4h** solo per i trigger di ingresso in ATR. Via il 5m. |
| S7 | Universo | Calcolato **automaticamente** ogni giorno come intersezione (vedi §4), non scelto a mano. |
| S8 | Dati prezzo | **Ibrido**: Binance dove la coppia esiste (dati puliti, storico lungo), fonte OHLC nativa del pool dove manca. Nessun token escluso solo perche' non e' quotato su Binance. |
| S9 | Venue | PancakeSwap V2 (provider esistente). |
| S10 | Validazione | **Nessuna ottimizzazione su backtest.** Verifica in dry-run a size ridotta, solo per controllare che i trigger scattino quando devono. |
| S11 | Uscite parziali | **Nessuna.** Niente take-profit, niente scarico: si esce solo per motivi strutturali. Sullo spot il tempo e' gratis, la posizione resta intera finche' la struttura regge (N13). |
| S12 | Scheduling | **Guidato dalle candele chiuse**, mai dall'orologio di sistema (N10). |
| S13 | Stato fra riavvii | In `runtime_state`, con ripristino **conservativo**: mai un'uscita spuria dopo un riavvio (N11). |
| S14 | Impatto sulla pool | Una tranche non supera il **3%** delle riserve (N14). |
| S15 | Validazione esecuzione | **Quote in ombra** in dry-run: si interroga PancakeSwap in sola lettura per misurare divergenza, slippage e impatto, senza eseguire (N15). |
| S16 | Grafici | Tranche d'acquisto, uscite col motivo, medie 50g/20g e marker di stato — sul grafico **live**, non solo a posizione chiusa (N16). |
| S17 | UI | Fase F9b completa: semaforo del regime, radar per percentile, motivo di esclusione, stato della scala, parametri editabili dall'app (N12). |

### Questioni aperte (da decidere prima dell'implementazione)

| # | Domanda | Nota |
|---|---|---|
| Q1 | Come si popola `SPOT_TOKEN_MAP`? Manuale curata, o si collega il risolutore CMC? | Vedi §3 — è il blocco principale. **Indizio**: in HEAD esiste già il test `test_build_spot_swap_params_resolves_via_cmc`, che si aspetta un kwarg `token_resolver` di `AgentService` **mai implementato** (il test fallisce da prima di questo piano). Il cablaggio CMC è stato tentato e abbandonato: capire perché prima di ripercorrerlo. |
| Q2 | Il passaggio a mainnet: oggi `execute_swap` è gated e `execution_mode=live` impone `bsc_network=testnet` | Serve una decisione operativa separata |
| ~~Q3~~ | ~~Numero massimo di posizioni~~ | ✅ **RISOLTA (2026-09-02)**: **8 posizioni**, ~11% ciascuna. Piu' slot da riempire = motore piu' attivo, e meno capitale per singola coin. |
| Q4 | Il vecchio motore si rimuove o si tiene dietro un flag di rollback? | Proposta: flag, rimozione dopo validazione |
| ~~Q5~~ | ~~Dedup incrociato spot/perp~~ | ✅ **RISOLTA ed ESEGUITA (2026-08-31)**: rimosso. Il dedup è ora **per mercato** (`manager.py`), spot e perp indipendenti sullo stesso asset. |
| ~~Q6~~ | ~~Heartbeat trade giornaliero~~ | ✅ **RISOLTA ed ESEGUITA (2026-08-31)**: rimosso del tutto (funzione, costanti, chiamata in `slow_tick`, chiave di risposta, test). |
| ~~Q7~~ | ~~Cooldown incrociato spot/perp~~ | ✅ **RISOLTA ed ESEGUITA (2026-08-31)**: `_in_cooldown` interroga ora **solo** il repository del mercato del segnale. Un trade perp non blocca più un ingresso spot sullo stesso asset. |

---

## 3. BLOCCO PRINCIPALE — la mappa indirizzi BSC

**Oggi nessun token è eseguibile su PancakeSwap.**

- `backend/app/core/config.py` — campo `spot_token_map: dict[str, str]` (alias `SPOT_TOKEN_MAP`),
  formato `simbolo -> "indirizzo"` oppure `"indirizzo:decimals"` (default 18).
- `.env.example` — `SPOT_TOKEN_MAP=` è **vuoto**. Anche `SPOT_QUOTE_TOKEN_ADDRESS` è vuoto.
- `backend/app/agent/service.py` — `_resolve_token_address(symbol)` guarda **solo** quella mappa.
- `_build_spot_swap_params` — senza indirizzo il trade esce con
  `{"status": "skipped", "reason": "spot_token_not_mapped"}`.

Esiste `backend/app/data/market_data/cmc.py` `resolve_contract_address` ma
**non è collegato** a `_resolve_token_address`.

La risoluzione per ticker è **deliberatamente rifiutata**
(docstring del modulo `venue_availability.py`): un ticker corrisponde a più
token BEP20 e "BTC" risolve a un token non correlato. Quindi la mappa va **curata e
verificata**, non dedotta.

### Lavoro richiesto

1. Per ogni ticker candidato: indirizzo BEP20 + decimals, verificato su BscScan.
2. File versionato (es. `configs/bsc_token_map.yaml`) invece che solo variabile d'ambiente,
   così la mappa sta in git ed è rivedibile. `SPOT_TOKEN_MAP` resta come override.
3. Valorizzare `SPOT_QUOTE_TOKEN_ADDRESS` (USDT BSC).
4. Script di verifica: per ogni voce controlla che `getPair` restituisca una pool
   e che la liquidità superi la soglia.

---

## 4. LA STRATEGIA

### 4.1 Interruttore generale di regime (nuovo)

Valutato una volta al giorno su candele daily:

Entrambe le condizioni hanno **isteresi**: soglia diversa per accendere e per spegnere.

| Condizione | Accende | Spegne |
|---|---|---|
| Trend BTC (daily) | prezzo sopra la **EMA 20** | prezzo sotto la **EMA 50** |
| Salute delle alt (% universo sopra la propria media 50g) | sopra **45%** | sotto **35%** |

Fra le due soglie non succede nulla: si resta nello stato in cui si era.

**Perche' asimmetrico.** Una media lenta (100g) tiene fuori dai rialzi che capitano
dentro un bear, e puo' lasciare lo spot fermo per mesi. Una media veloce simmetrica
farebbe l'opposto: BTC incrocia la EMA 20 di continuo in fase laterale. Prendendo la
EMA 20 per accendere e la EMA 50 per spegnere si e' rapidi a cogliere il rialzo e
lenti a mollarlo — la stessa logica gia' usata per la forza relativa (75° entra,
50° esce).

**Spento non vuol dire vendere (S18).** Il regime blocca **solo gli acquisti**:
nessun nuovo ingresso, nessuna tranche aggiuntiva. Le posizioni aperte continuano a
essere gestite dalle proprie uscite per asset. Se il regime liquidasse, ogni falso
segnale costerebbe un giro completo di fee su tutte le posizioni — con una media
veloce diventerebbe il costo dominante.

La terza condizione è quella che manca oggi ed è la più importante: intercetta il
caso "BTC tiene, le alt scendono", che il filtro attuale non vede.

### 4.2 Universo (calcolato ogni giorno)

Intersezione di:

1. presente in `configs/eligible_tokens.yaml` (148 ticker)
2. indirizzo BSC mappato e verificato
3. pool PancakeSwap esistente sul percorso `USDT → WBNB → token` (`getPair` ≠ zero)
4. liquidità pool ≥ soglia (`risk_min_pool_liquidity_usd`, default 50.000 $)
5. storico prezzi disponibile con ≥ 250 candele daily, da Binance **oppure** dal pool
6. non è una stablecoin (`SPOT_EXCLUDED_STABLECOINS`)

Il risultato **sostituisce la watchlist spot scelta a mano**. La selezione manuale
resta come eventuale restrizione ulteriore, non come sorgente.

### 4.3 Forza relativa

Su chiusure daily:

```
RS = (prezzo_coin_oggi / prezzo_coin_14g_fa) / (prezzo_btc_oggi / prezzo_btc_14g_fa)
```

`RS > 1` ⇒ batte BTC. Si ordina l'universo per RS e si lavora sul **percentile**,
non sul valore assoluto. Finestra **14 giorni** su chiusure daily: nel crypto le
rotazioni durano settimane, e a 30 giorni ci si accorgeva di un nuovo leader con
circa due settimane di ritardo.

| Soglia | Valore |
|---|---|
| Entra nel radar | percentile ≥ **75** |
| Esce per debolezza | percentile < **50** per **5 giorni consecutivi** |

Le due soglie sono diverse di proposito (isteresi): senza banda morta una coin che
oscilla intorno alla soglia genera rotazione continua, e su PancakeSwap ogni
rotazione costa LP fee + slippage + gas.

Condizione aggiuntiva per entrare nel radar: **prezzo sopra la propria media 50g,
con media in salita**.

Casa naturale: `backend/app/agent/signals/spot/relative_strength_v2.py`, oggi uno
stub `NotImplementedError` riservato esattamente a questo.

### 4.4 Ingresso — scala a 3 tranche

Trigger: ritracciamento dal massimo a 10 giorni, misurato in ATR (4h).

| Tranche | Trigger | Size |
|---|---|---|
| 1ª | −1,0 ATR dal massimo 10g | **50%** |
| 2ª | −1,0 ATR sotto la 1ª | **30%** |
| 3ª | −1,0 ATR sotto la 2ª | **20%** |

Tutti i valori della tabella sono **configurabili dall'app** (soglia della 1ª tranche,
passo fra le tranche, frazioni, periodo e timeframe dell'ATR): vedi F9b.

Size decrescente: il grosso sul primo storno, che dentro un trend è quello con più
probabilità di bastare. Le tranche successive coprono lo storno profondo senza
spostare il peso sull'ipotesi peggiore.

**Condizione di annullamento della scala:** se prima della 2ª o 3ª tranche l'asset
**chiude sotto la propria media 50 giorni**, la scala si ferma. Non è più un
ritracciamento, è un cambio di trend. Le tranche residue non si eseguono; la
posizione resta parziale e passa alla gestione delle uscite.

Questo è il presidio che mancava: senza, si media fino in fondo anche dopo la
rottura della struttura.

#### Vincolo architetturale (verificato sul codice)

**Le tranche 2 e 3 NON possono passare dal percorso di ingresso normale.** Due
guardie le rifiuterebbero, entrambe confermate leggendo il codice:

- `risk/manager.py` (blocco dedup in `RiskManager.evaluate`) — dedup per-asset: se esiste già una
  posizione aperta su quell'asset (spot **o** perp) la decisione è
  `asset_already_open`. La 2ª tranche verrebbe respinta qui.
- `service.py` `_in_cooldown` — blocca se esiste un trade
  sull'asset entro `spot_cooldown_minutes` (default 30). Le tranche distano minuti
  o ore: verrebbero respinte qui. Attenzione: **anche i trade di chiusura sono righe
  `SpotTrade`**, quindi pure uno scarico parziale fa ripartire il cooldown.

Conseguenza di progetto: **la scala è un'estensione di `_maybe_scale_in_spot`**
(add sulla posizione esistente, con ricalcolo della entry media ponderata), non una
sequenza di segnali d'ingresso. Il percorso di add **non** attraversa dedup né
cooldown, quindi funziona — ma va invertito nella condizione: oggi aggiunge solo
**a favore** (`price <= pos.entry_price` → return, `_maybe_scale_in_spot`), a noi serve
che aggiunga **contro**, con la struttura ancora integra.

Si riusa dunque la meccanica di media ponderata già esistente e si sostituisce solo
il blocco di condizioni.

#### Sizing della prima tranche

Oggi `nominal_size = equity * cap_pct/100` (`RiskManager.evaluate`, calcolo `nominal_size`) è **l'intera size del
trade**. Con la scala, la 1ª tranche deve valere il **50% del budget per asset**, e il
budget pieno è `cap_pct`. Serve quindi che l'ingresso iniziale sia dimensionato a
frazione, non a size piena — altrimenti la 1ª tranche consuma già tutto il tetto e
il cap del percorso di add (`_maybe_scale_in_spot`, `room = cap - current_notional`)
azzera le tranche successive.

### 4.5 Uscite (tutte strutturali)

| Priorità | Uscita | Condizione | Attiva quando | Quota |
|---|---|---|---|---|
| 1 | Rottura trend | chiusura **daily** sotto media **20 giorni** | **solo a scala conclusa** (N1) | tutto il residuo |
| 2 | Debolezza relativa | percentile RS < 50 per 5 giorni | sempre | tutto il residuo |

Il regime **non compare fra le uscite** (S18): spegnendosi blocca gli acquisti, non
vende. In un crollo vero sono queste due a scattare, e in fretta.

"Scala conclusa" = tutte e tre le tranche eseguite, **oppure** scala annullata per
rottura della media 50g, **oppure** scala scaduta per `ladder_expiry_bars` (N2).
Mentre la scala è aperta l'unico presidio è la condizione di annullamento: l'uscita
2 è sospesa, altrimenti comprerebbe e venderebbe lo stesso movimento.

**Nessuno scarico parziale (deciso, N13).** Si esce solo per i due motivi qui sopra.
Un take-profit parziale sarebbe lo stesso errore del vecchio TP1 che questo piano
boccia in §1: taglia la vincita presto. Sullo spot il tempo non costa nulla, quindi
la posizione resta intera finché la struttura regge — e i due swap risparmiati per
posizione rendono le fee DEX una voce trascurabile invece che un problema.

Nessun TP2, nessun trailing percentuale, nessun breakeven, nessuno stop di prezzo.
Il "trailing" è la media 20g daily: si segue la struttura, non una distanza fissa.

### 4.6 Portafoglio

Il capitale spot e' una **fetta separata** dell'equity tradabile (S19), di default
il **40%**. Tutte le percentuali qui sotto sono riferite a quella fetta, non
all'equity totale.

| Vincolo | Valore |
|---|---|
| Fetta spot | **40%** dell'equity tradabile (il resto al perp) |
| Posizioni massime | **8**, ma solo se il capitale lo consente (S20) |
| Peso per asset a scala piena | **11%** della fetta spot |
| Nuove prime tranche nelle stesse 24h | max 2 |
| Capitale non impiegato | resta in USDT, nessun obbligo di essere investito |

Il limite sulle prime tranche giornaliere è la difesa contro il giorno di storno
generale in cui tutto l'universo triggera insieme: nel crypto le posizioni aperte
lo stesso giorno sono, di fatto, un trade solo.

### 4.7 NODI LOGICI — problemi trovati rileggendo il piano

> Sezione aggiunta nella 3ª revisione. I primi due sono difetti che romperebbero la
> strategia in produzione, non rifiniture.

#### N1 — 🔴 L'ingresso e l'uscita si contraddicono

L'ingresso compra a **−1,5 ATR dal massimo a 10 giorni**. L'uscita 2 chiude alla
**chiusura sotto la media 20 giorni**. Un ritracciamento di 1,5 ATR porta molto
spesso il prezzo *sotto* la media 20g: si comprerebbe e si verrebbe espulsi
immediatamente, pagando due volte le fee su DEX. Le due regole, così, si annullano.

**Soluzione proposta:** l'uscita per rottura del trend usa la media **20 giorni su
daily** (non su 4h) e si attiva **solo a scala completata o annullata**, mai mentre
la scala è in corso. Durante la costruzione della posizione l'unico presidio è la
condizione di annullamento (chiusura sotto la media 50g), che è più lenta e non
confligge col ritracciamento cercato.

#### N2 — 🔴 La scala può restare incompiuta per sempre

Se la 1ª tranche entra e il prezzo **riparte subito verso l'alto**, le tranche 2 e 3
non scattano mai: la posizione resta al 50% del budget a tempo indeterminato. Il
risultato è essere **sistematicamente sotto-investiti proprio sui vincitori**, cioè
l'errore opposto a quello che il piano vuole correggere.

**Soluzione proposta:** la scala ha una **scadenza**. Se entro `ladder_expiry_bars`
(proposta: 30 candele 4h = 5 giorni) le tranche residue non scattano, la scala si
**chiude**: il budget non speso viene liberato e la posizione prosegue con la size
raggiunta. Va deciso se in alternativa completare la size a mercato — sconsigliato,
comprerebbe forza invece che debolezza, contro S2.

#### N3 — ~~Ordine di precedenza tra scala e primo scarico~~ (SUPERATO da N13)

Il primo scarico è a **+2 ATR dal costo medio**. Ma il costo medio si abbassa a ogni
tranche. Se si scarica il 30% e poi il prezzo scende facendo scattare la tranche
successiva, si **ricompra ciò che si è appena venduto**, pagando due volte le fee.

**Superato:** con la decisione N13 lo scarico parziale non esiste più, quindi il
conflitto sparisce alla radice. Resta valido il principio generale: mentre la scala
è aperta non si vende.

#### N4 — ~~"Chiudere sul primo rimbalzo utile"~~ (SUPERATO da S18)

L'uscita 1 (regime spento) dice di chiudere "sul primo rimbalzo utile": non è una
condizione, è un'intenzione.

**Superato:** con S18 il regime non liquida piu', quindi non esiste nessuna
"chiusura da regime" da definire. Il problema sparisce alla radice.

#### N5 — Percentili instabili su un universo piccolo

Se dopo i filtri di §4.2 l'universo scende a ~20 asset, il percentile 75 sono i
primi 5 e il percentile 50 i primi 10: fra la soglia d'ingresso e quella d'uscita
ci sono **cinque posizioni**. Basta che un token entri o esca dall'universo perché i
percentili di tutti si spostino, e l'isteresi progettata sparisce.

**Soluzione proposta:** definire una **dimensione minima dell'universo**
(`rs_min_universe`, proposta: 25). Sotto quella soglia si passa da percentile a
**soglia assoluta** (entra se `RS > 1,05`, esce se `RS < 0,95` per 5 giorni), che non
dipende dalla numerosità. La misura dell'universo in F2 dice quale dei due regimi
sarà quello normale.

#### N6 — Prezzo del segnale (Binance) ≠ prezzo di esecuzione (pool BSC)

S8 fa arrivare i dati da Binance, S9 esegue su PancakeSwap. Sui token Binance-Peg il
prezzo di pool può divergere, e tutti i livelli (ritracciamento, ATR, scarico) sono
calcolati su una serie che **non è quella su cui si compra**.

**Soluzione proposta:** i livelli restano calcolati su Binance (è l'unica serie
storica disponibile), ma prima di ogni esecuzione si confronta il prezzo di quote
PancakeSwap col prezzo Binance: **se divergono oltre `max_price_divergence_pct`
(proposta: 1,5%) il trade si salta** e si logga. È anche un rilevatore di pool
illiquide che i filtri di §4.2 non hanno intercettato.

#### N7 — Asset che esce dall'universo mentre è in posizione

Non definito. **Soluzione proposta:** se un asset esce dall'universo per liquidità o
per dati mancanti, **non si aprono nuove tranche** ma la posizione non viene
liquidata d'ufficio; resta gestita dalle uscite normali. Se esce perché la pool è
sparita, si chiude appena eseguibile.

#### N8 — Size minima della terza tranche

Con budget per asset al 18% dell'equity e la scala 50/30/20, la 3ª tranche vale il
**3,6% dell'equity**. Va verificato che resti sopra `min_trade_size_usd` e che il gas
BSC non se la mangi. **Soluzione proposta:** se una tranche calcolata sta sotto il
minimo eseguibile, viene **accorpata alla precedente** invece che eseguita a parte.

#### N9 — Migrazione dalle posizioni del vecchio motore

All'accensione del nuovo motore possono esistere `SpotPosition` aperte create dal
vecchio, con TP1/TP2/trailing valorizzati e senza i campi della scala.

**Soluzione proposta:** le posizioni preesistenti restano gestite dalle **vecchie
uscite** fino a chiusura naturale (flag `engine="v1"` sulla posizione), e il nuovo
motore non le tocca. Nessuna migrazione di stato, nessuna chiusura forzata.

### 4.8 NODI OPERATIVI — cosa manca per farlo davvero girare

> Sezione aggiunta nella 5ª revisione. §4.7 copre la logica; questa copre l'impianto
> che la fa funzionare in produzione. Erano tutti buchi scoperti, non rifiniture.

#### N10 — ✅ DECISO: guidato dalle candele, non dall'orologio

Il piano parla di calcoli "giornalieri" e trigger "ogni 4 ore", ma l'unico ciclo che
esiste e' `slow_tick`, che gira a intervalli di minuti. Mancava del tutto la
risposta a: a che ora si ricostruisce l'universo, quando si calcola la classifica,
cosa succede se il bot e' spento a quell'ora, cosa succede al riavvio.

**Soluzione proposta — tutto guidato dalle candele, non dall'orologio.**

- *Passata giornaliera* (universo, classifica RS, regime): parte da `slow_tick`
  quando la **data UTC dell'ultima candela daily chiusa** e' piu' recente di quella
  dell'ultima passata registrata. Se il bot era spento, recupera al primo tick utile.
- *Trigger 4h* (tranche, uscite): agiscono solo quando compare una **nuova candela
  4h chiusa** per quell'asset, confrontando il timestamp dell'ultima elaborata.

Ancorare tutto al timestamp delle candele invece che all'ora di sistema evita anche
la trappola nota del clock simulato in dry-run (data di sistema disallineata dalle
klines reali): il motore non guarda mai `now`, guarda l'ultima candela chiusa.

#### N11 — ✅ DECISO: `runtime_state` con ripristino conservativo

Lo stato della posizione sta nel DB (§5.6), ma tre cose non avevano casa:

| Stato | Perche' serve |
|---|---|
| stato del regime (acceso/spento + soglia usata) | con l'isteresi 45/35 serve ricordare **da dove si viene**, altrimenti al riavvio si sceglie la soglia sbagliata |
| contatore "giorni sotto il percentile 50" per asset **non in posizione** | serve al radar, e sulla posizione non c'e' |
| quali asset sono gia' nel radar | altrimenti al riavvio rientrano tutti insieme |

**Soluzione proposta:** chiavi in `runtime_state` (dove gia' vivono le impostazioni
mobile): `spot_v2_regime`, `spot_v2_rs_state`, `spot_v2_last_daily_pass`.
Se mancano, si ricalcola cio' che e' derivabile (i percentili) e si azzerano i
contatori in modo **conservativo**: `weak_days = 0`, cosi' un riavvio non provoca
mai un'uscita spuria.

#### N12 — ✅ DECISO: UI completa (fase F9b)

La scheda Agente oggi mostra i punteggi del vecchio motore. Col nuovo non resta
niente da vedere, e i parametri nuovi non sono in `AgentMobileSettings`, quindi non
sarebbero modificabili dall'app.

**Soluzione proposta:** nuova fase **F9b** con semaforo del regime (e quale delle tre
condizioni manca), radar ordinato per percentile RS, motivo di esclusione per ogni
token scartato (F2 lo produce gia'), stato della scala per posizione, e i parametri
di §7 aggiunti allo schema mobile.

#### N13 — ✅ DECISO: nessuno scarico parziale

Costruire una posizione piena sono **3 swap**, chiuderla 1 o 2. Su PancakeSwap ogni
swap costa LP fee 0,25% + gas + slippage: un ciclo completo sta **sopra l'1%**.
Il primo scarico a +2 ATR (su base 4h) non e' garantito che lo copra.

**Ma la diagnosi giusta e' un'altra**: se l'1% di fee intacca il bersaglio, e' il
bersaglio a essere sbagliato, non la soglia. +2 ATR su 4h e' un movimento piccolo:
era **lo stesso errore del vecchio TP1** che questo piano boccia in §1 ("vincite
tagliate presto"), reintrodotto con un altro nome.

**Decisione: lo scarico parziale si elimina.** Si esce solo per motivi strutturali.
Conseguenze:
- due swap in meno per posizione, quindi i costi DEX diventano trascurabili;
- si punta a movimenti da decine di punti, dove l'1% non conta;
- coerente con la natura dello spot: il tempo e' gratis, la posizione resta intera
  finche' la struttura regge.

Nessuna soglia minima da introdurre, nessun asset da escludere per bassa volatilita'.

#### N14 — ✅ DECISO: tetto al 3% delle riserve

Il filtro chiede pool >= 50.000 $, ma se il capitale cresce una tranche da 18%
dell'equity **muove il prezzo da sola**. Nessuna regola lo impediva.

**Decisione:** la singola tranche non supera `max_pool_impact_pct`
(default **3%**) delle riserve della pool. Sopra soglia, la tranche si riduce; se
nemmeno la minima ci sta, l'asset viene escluso. Dipende dai fix B1/B3, perche' oggi
la misura della liquidita' e' sbagliata per i token con decimals != 18.

#### N15 — ✅ DECISO: quote in ombra nel dry-run

F10 verifica che i trigger scattino, ma il dry-run simula i riempimenti a prezzi
Binance: **non tocca PancakeSwap**. Slippage reale, divergenza di prezzo (N6), gas e
swap falliti resterebbero non testati fino al mainnet (Q2).

**Soluzione proposta — "quote in ombra":** durante il dry-run, per ogni trade
simulato si chiama comunque `get_quote` di PancakeSwap in sola lettura e si
registrano divergenza, slippage implicito e impatto sulla pool, **senza eseguire**.
Costa nulla, non rischia nulla, e valida in anticipo N6, N14 e la misura di
liquidita'.

#### N16 — ✅ DECISO: tranche, uscite col motivo, medie 50g/20g, marker — anche live

`_snapshot_closed_trade` costruisce un payload con **un solo `entry_price` e un solo
`exit_price`**, piu' i livelli SL/TP1/TP2. Con la scala a 3 ingressi, uno scarico
parziale e un'uscita finale, il grafico mostrerebbe solo il prezzo medio: si
perderebbe esattamente cio' che serve capire — dove hai comprato ogni tranche e
perche' sei uscito.

**Soluzione proposta:** il payload passa da valori singoli a liste.

| Campo | Contenuto |
|---|---|
| `entries[]` | per ogni tranche: timestamp, prezzo, size, indice (1/2/3) |
| `exits[]` | per ogni uscita: timestamp, prezzo, size, motivo (scarico / trend / RS / regime) |
| `levels` | le serie **media 50g e media 20g** — sono le regole vere di uscita, al posto delle rette SL/TP che non esistono piu' |
| `markers` | scala annullata, scala scaduta, regime spento, debolezza RS |

Vale per il grafico **live**, non solo per lo snapshot alla chiusura: con posizioni
che durano settimane, vedere la scala mentre si costruisce e' piu' utile del
consuntivo.

⚠️ **Prerequisito:** oggi l'unico legame fra un trade e la sua posizione e' il
**prefisso del `trade_id`** (limite gia' annotato nel golden test). Per ricostruire
in modo affidabile tranche e uscite serve `position_id` come **colonna vera** su
`SpotTrade`. Va fatto prima di F8b.

---

---

## 5. AUDIT DEL CODICE SPOT ESISTENTE

> Questa è la sezione da rileggere con più attenzione. Molti meccanismi attuali
> **lavorano contro** il nuovo modello e vanno disattivati prima, non dopo.

### 5.1 Conflitti diretti — da spegnere

| # | Cosa | Dove | Perché è un problema |
|---|---|---|---|
| C1 | **Scale-in E v3** | `service.py` `_maybe_scale_in_spot` | ✅ verificato. Aggiunge solo a favore: `if price <= pos.entry_price: return` , stop già a breakeven, nuovo higher-high richiesto. La nostra scala aggiunge **contro**. **Da riscrivere invertendo le condizioni**, riusando la media ponderata e il cap già presenti. È il percorso corretto per le tranche (vedi §4.4). |
| C2 | **TP1 / TP2** | `momentum.py` (calcolo TP), `_check_sl_tp` | TP1 chiude il 60% a 2,5 ATR. Nel nuovo modello **non esiste alcun take-profit** (N13): si esce solo per motivi strutturali. Se restano attivi, chiudono le posizioni prima della logica nuova. |
| C3 | **Trailing + breakeven + profit lock** | `service.py` `_check_sl_tp` | Sostituiti dalla media 20g. L'ordine di priorità delle uscite (`_check_sl_tp`) li fa scattare **per primi**: resterebbero loro a comandare. |
| C4 | **Stop loss (ATR / lowest)** | `momentum.py` (calcolo stop) | S4: nessuno stop di prezzo. **Soluzione verificata: emettere `stop_loss = None`.** In `RiskManager.evaluate` tutto il blocco sul sizing è dentro `if intent.stop_loss is not None`, quindi con `None` si saltano *insieme* il filtro I e il sizing per distanza di stop, e `risk_size` resta `nominal_size`. Pulito, nessuna modifica al risk manager. |
| C5 | **Filtro I — max stop distance** | `risk/manager.py` (`RiskManager.evaluate`) | ✅ verificato: attivo solo con `stop_loss is not None`. Risolto da C4 senza toccarlo. Da spegnere comunque via config per chiarezza. |
| C8 | **Heartbeat trade giornaliero** | `service.py` `_daily_trade_heartbeat` | ✅ **RIMOSSO (2026-08-31).** `slow_tick` forzava un trade spot su ETH se entro le 20:00 UTC non ne era stato fatto nessuno (retry fino alle 23:30): guardrail legacy della competizione, incompatibile con una strategia selettiva. Rimossi funzione, costanti `DAILY_TRADE_*` / `HEARTBEAT_TRADE_*`, chiamata, chiave `daily_trade_heartbeat` nella risposta e i due test dedicati. Resta inutilizzato il setting `minimum_trades_per_day` (con guardrail di boot in `config.py` `validate_hard_guardrails` che ne impone ≥ 1): innocuo, da ripulire in F11. |
| C6 | **Regime BTC 15m + market reversal** | `momentum.py` / `service.py` | Due sistemi di regime che si contraddicono. Il nuovo è daily e include la salute delle alt. Il vecchio va rimosso, non stratificato. |
| C7 | **Gate d'ingresso momentum** | `momentum.py` `evaluate` | `volatility_trigger_pct`, `relative_volume_threshold`, `trend_score`, `extension_ok`, `confidence_threshold`: tutto il gate assoluto è sostituito dalla selezione cross-sezionale. |

### 5.2 Da verificare — possibili blocchi silenziosi

| # | Cosa | Dove | Rischio |
|---|---|---|---|
| V1 | **Cooldown per asset** | `service.py _in_cooldown` | ✅ **Risolto su due fronti (2026-08-31).** (a) Reso **per mercato**: interroga solo il repository del mercato del segnale, un trade perp non blocca più lo spot. (b) Le tranche restano comunque instradate sul percorso di add (§4.4), che non attraversa il cooldown. Resta valido il promemoria: dentro lo spot anche le **chiusure** sono righe `SpotTrade`, quindi uno scarico parziale fa ripartire il cooldown sui *nuovi ingressi* di quell'asset (non sulle tranche). |
| V2 | **Dedup asset** | `risk/manager.py` | ✅ **RISOLTO (2026-08-31).** Il dedup è ora **per mercato**: una posizione perp aperta non blocca più lo spot sullo stesso asset. Resta il dedup dentro lo stesso mercato (una sola `SpotPosition` per asset), che è quello che ci serve: la scala è una posizione con più fill. Test aggiunto: `test_risk_engine_dedup_is_per_market_not_cross_market`. |
| V3 | **Filtro H — spike ATR** | `momentum.py` (filtro anti-spike "H v3") | Blocca se `ATR_now/ATR_avg(50) > 3`. In un bull market gli allunghi hanno ATR alto: rischia di escludere proprio i leader. Da rivalutare, probabilmente da spegnere. |
| V4 | **Time stop G v3** | `service.py` `_spot_time_stop_reason` | Oggi disattivato. Verificare che resti spento: le posizioni del nuovo modello devono poter durare settimane. |
| V5 | **Warmup / cache candele 5m** | `momentum.py` `_warmup_candles`, `ohlcv_warmup.py` | Il warmup scarica 5m con TTL 240s. Il nuovo modello usa daily + 4h: serve un warmup diverso e uno storico daily ≥ 250 candele per la media 200 e la forza relativa. |
| V6 | **Bug candela in formazione** | (già noto) | Il fix esistente valuta su candele chiuse. Va mantenuto anche nel nuovo calcolo su daily/4h: la candela daily corrente non è chiusa. |
| V7 | **Ordine di scansione della watchlist** | `service.py` `slow_tick` | Loop in ordine di lista: la prima coin che passa prende lo slot. Con una classifica per forza relativa l'ordine **deve** diventare l'ordine di ranking, non quello della watchlist. |

### 5.3 Bug esistenti da correggere in corsa

| # | Bug | Dove |
|---|---|---|
| B1 | `spot_pool_liquidity_usd` divide per `10**18` **hardcoded** | `venue_availability.py` `spot_pool_liquidity_usd` — token con decimals ≠ 18 producono liquidità sbagliata di ordini di grandezza |
| B2 | Il guard liquidità è `if intent.liquidity_usd is not None` | `risk/manager.py` (guard liquidità in `evaluate`) — una pool **non misurabile** passa senza controllo |
| B3 | La liquidità misura **solo l'ultimo hop** del percorso | `venue_availability.py` `spot_pool_liquidity_usd` — ignora la profondità del primo hop |
| B4 | `docs/Strategia_Spot.md` dice che gli indirizzi si risolvono via CMC | Non è vero nel codice: documentazione da aggiornare |

### 5.4 Da riusare così com'è

- `PancakeSwapProvider` — quote, path, approve, swap (`pancakeswap_provider.py`)
- `VenueAvailabilityService._spot_status` — pool discovery (con i fix B1/B3)
- `AsyncRateLimiter` (`market_data/rate_limit.py`) per il backfill daily
- `indicators.py` — `ema`, `atr`, `atr_series`, `percentile_rank`, `sanitize_candles`
- `BinanceKlineFeed.fetch(..., start_time=...)` per lo storico daily
- Guardrail di rischio non legati allo stop: liquidità, esposizione, daily loss limit
- Esclusione stablecoin (`SPOT_EXCLUDED_STABLECOINS`)

### 5.5 Memorie di progetto che diventano obsolete

Riguardano tutte il vecchio modello a TP/SL/trailing e vanno riviste a fine lavoro:
filtro volatilità spot (`max_stop_distance_pct`), trailing dopo TP1, Smart Stop
Loss, modello protezione/uscite. Il bug della candela in formazione resta valido
(V6).

### 5.6 Schema DB — campi da aggiungere

`SpotPosition` (`backend/app/persistence/models/positions.py`) ha già:
`entry_atr`, `max_price`, `scale_in_count`, `tp1_reached`, `initial_stop_loss`,
`swap_fee_usd`, `slippage_usd`, `fee_mode`.

Mancano, e servono al nuovo modello:

| Campo | Uso |
|---|---|
| `ladder_budget_usd` | budget totale pianificato per l'asset (le tranche sono frazioni di questo) |
| `ladder_filled` | quante tranche eseguite. **Non riusare `scale_in_count`**: resta al vecchio motore finché esiste il flag di rollback (Q4), riusarlo rende ambiguo lo stato |
| `ladder_state` | `open` / `complete` / `cancelled` / `expired` — governa l'attivazione dell'uscita per rottura trend (N1) |
| `ladder_deadline` | scadenza della scala (N2) |
| `last_tranche_price` | riferimento per il trigger della tranche successiva (−1 ATR sotto) |
| `rs_weak_days` | contatore giorni consecutivi con RS sotto soglia |
| `entry_ref_high` | massimo a 10 giorni (= 60 candele 4h) al momento del segnale, base del ritracciamento |
| `engine` | `v1` / `v2`: le posizioni del vecchio motore restano gestite dalle vecchie uscite (N9) |

⚠️ **`max_price` non è riutilizzabile per i trigger della scala**: è il massimo
*dall'ingresso* (watermark alto, aggiornato in `_check_sl_tp`), serve al trailing.
La scala ha bisogno del riferimento opposto — il prezzo dell'ultima tranche — e del
massimo a 10 giorni, che è una finestra mobile di mercato, non uno stato di posizione.

⚠️ **Non c'è Alembic**: lo schema nasce da `create_all`. Le colonne nuove vanno
aggiunte col pattern `upgrade_schema` già usato altrove nel progetto (vedi
`Plan_Reserve.md` D26), oppure serializzate in un campo JSON di stato.

### 5.8 INTEGRAZIONE con la struttura attuale — problemi trovati

> Passata dedicata (6ª revisione): non "il piano è coerente con sé stesso", ma
> "il piano funziona dentro CryptoSentinel com'è fatto oggi". Due voci sono
> **bloccanti**: senza risolverle il motore nuovo non comprerebbe, o comprerebbe e
> non venderebbe mai.

| # | Problema | Gravità |
|---|---|---|
| I1 | Il brain scarta ogni trade del motore nuovo | 🔴 bloccante |
| I2 | `spot_max_exposure_pct` a 30% strozza il portafoglio a ~3 posizioni | 🔴 bloccante |
| I3 | I token solo-DEX resterebbero bloccati in posizione per sempre | 🔴 bloccante |
| I4 | `slow_tick` è un ciclo per-asset, il modello è cross-sezionale | struttura |
| I5 | `_scanner_payload` costruisce sempre un simbolo Binance | struttura |
| I6 | Il vecchio filtro di regime vive in `evaluate_spot`, non nel segnale | precisione |
| I7 | Tre tranche = tre notifiche "trade aperto" | rumore |
| I8 | Lo snapshot del grafico dipende da SL/TP che non esistono più | grafici |
| I9 | Motivi di chiusura nuovi non mappati | minore |
| I10 | Volume delle `AgentDecision` | nota positiva |

#### I11 — 🔴 Spot e perp attingono dallo stesso capitale, senza tetto complessivo

`RiskManager.evaluate` calcola la size su `total_equity_usd` (meno la Riserva) **per
entrambi i mercati**. L'unica separazione sono due tetti indipendenti
(`spot_max_exposure_pct`, `perp_max_exposure_pct`), e **ciascuno conta solo le
proprie posizioni**: quello spot somma il nozionale spot, quello perp somma il
margine perp. Non esiste nessun guard complessivo.

Con i default attuali (30 + 30) il problema era latente. Portando lo spot al 90%
diventerebbe immediato: su 1.000 € farebbe 900 spot + 300 perp = **120% del
capitale**, e nulla lo bloccherebbe. In più i due motori si farebbero la corsa sullo
stesso denaro, con lo spot — che punta a stare quasi sempre investito — a
affamare il perp.

**Soluzione (S19):** budget separati. `RiskManager` riceve una **equity di mercato**
(equity tradabile × quota del mercato) invece dell'equity totale; tutte le
percentuali per-trade e di esposizione si riferiscono a quella. Il tetto complessivo
diventa automatico perche' le quote sommano a 100%.

#### N17 — 🔴 Il disegno non entra nel capitale attuale

Numeri reali (portafoglio dry-run, verificati sul DB): equity totale **883,74 €**,
Riserva **30,67 €**, quindi equity tradabile **853 €**. Fetta spot al 40% = **341 €**.

Con 8 posizioni all'11% e la scala 50/30/20:

| | valore |
|---|---|
| budget per posizione | 37,5 € |
| 1ª tranche | 18,8 € |
| 2ª tranche | 11,3 € |
| 3ª tranche | **7,5 €** |

La terza tranche sfiora il minimo tecnico di 7 €, e su BSC un ordine da 7 € paga in
gas oltre l'1%: economicamente non ha senso. **Le 8 posizioni sono un disegno da
conto piu' grande** (servono ~2.000 € di equity totale perche' tutte e tre le tranche
restino sopra i ~20 €).

**Soluzione (S20) — dimensionamento adattivo.** Si fissa `min_tranche_usd` (default
**20 €**, la soglia sotto la quale il gas pesa troppo) e da lì si ricava quante
posizioni il capitale sostiene:

```
budget_per_posizione = min_tranche_usd / frazione_tranche_piu_piccola
posizioni = min(max_posizioni, fetta_spot / budget_per_posizione)
```

Con la fetta attuale di 341 € e la scala 50/30/20 (frazione minima 20%):
budget minimo per posizione = 20 / 0,20 = 100 € → **3 posizioni** con scala piena.
Crescendo il capitale il numero sale da solo fino al tetto di 8.

Se nemmeno una posizione a scala piena ci sta, si riduce **prima il numero di
tranche** (da 3 a 2), mai a tranche unica: l'ingresso scalato e' un punto fermo (S3).

⚠️ **Nota di configurazione:** `configs/instance.yaml` ha
`dry_run_capital_usd: 200`, valore **stantio** — il portafoglio reale è partito da
1.000 €. Non ha effetto sul portafoglio esistente, ma se venisse reinizializzato
ripartirebbe da 200. Da allineare.

#### I1 — 🔴 Il brain scarterebbe ogni trade

`_handle_signal` passa sempre dal meta-controller. Nel fallback locale (senza API
key) la regola è: `quality >= 0.6` ⇒ `approve`, altrimenti `skip`. E
`_intent_from_signal` legge `quality` dal segnale con **default 0**.

Il motore nuovo non ha un "quality score": lo abbiamo sostituito con la selezione
cross-sezionale. Risultato: ogni ingresso uscirebbe come `skip`, per sempre, senza
alcun errore visibile.

**Soluzione:** il segnale emette `quality = percentile RS / 100`. Non è un numero
finto: è esattamente la misura di qualità del nuovo modello. E siccome nel radar ci
va solo il quartile alto, quality ≥ 0,75 per costruzione, quindi supera la soglia
0,60 in modo naturale. Il brain resta nel percorso e continua a poter bloccare.

#### I2 — 🔴 Il tetto di esposizione strozza il portafoglio

Valori attuali: `spot_capital_per_trade_pct` **6%**, `spot_max_exposure_pct` **30%**.
Il disegno nuovo vuole 8 posizioni all'11% ≈ 88% di esposizione. Con il tetto a 30%
il risk manager bloccherebbe intorno alla terza posizione con
`max_exposure_guard` — e il sintomo sarebbe **esattamente quello che vogliamo
evitare: il bot che sta fermo**, per un motivo di configurazione e non di mercato.

**Soluzione:** portare `spot_capital_per_trade_pct` a **11** e
`spot_max_exposure_pct` a **90** in `configs/`. ⚠️ Attenzione: questi due vivono anche
nell'**override runtime** delle impostazioni mobile, che vince sul file. Vanno
allineati entrambi, altrimenti il file dice una cosa e il bot ne fa un'altra.

#### I3 — 🔴 I token solo-DEX resterebbero bloccati in posizione

Con S8 abbiamo aperto l'universo ai token senza coppia Binance. Ma
`_refresh_position_prices` aggiorna `current_price` **solo** con il ticker Binance:
per quei token il prezzo non si aggiornerebbe mai, quindi le uscite non verrebbero
mai valutate e la posizione resterebbe aperta a tempo indefinito.

**Soluzione:** il refresh dei prezzi deve avere lo stesso fallback dei dati storici
(S8): ticker Binance dove esiste, quote del pool PancakeSwap altrimenti. Senza
questo, S8 introduce un bug peggiore del problema che risolve.

#### I4 — `slow_tick` è per-asset, il modello è cross-sezionale

Oggi il ciclo fa: per ogni asset → valuta → decide, in modo indipendente. Il nuovo
modello deve prima **ordinare tutti** e poi agire sui migliori.

**Soluzione:** non serve riscrivere il ciclo. La passata giornaliera (N10) calcola
classifica e regime e li salva in `runtime_state` (N11); il ciclo per-asset legge
quel contesto già pronto. Cambia solo **l'ordine di iterazione**, che diventa
l'ordine di ranking invece di quello della watchlist (V7).

#### I5 — `_scanner_payload` costruisce sempre `{ASSET}USDT`

Il simbolo Binance è costruito per concatenazione. Per un token solo-DEX quel
simbolo non esiste, il fetch fallisce in silenzio e l'asset viene scartato con
`insufficient_ohlcv_history`.

**Soluzione:** il payload porta `price_source` (`binance` | `pool`) e il riferimento
corrispondente (simbolo o indirizzo pool); il modulo di segnale sceglie la fonte.

#### I6 — Il vecchio regime non vive dove pensavamo

`_spot_market_regime` e `_market_reversal_filter` sono chiamati **dentro
`evaluate_spot`**, non dentro il modulo di segnale. Spegnere il vecchio motore
(C6) richiede quindi di intervenire lì, non solo in `momentum.py`. Dettaglio di
precisione per F6, ma è il genere di cosa che fa perdere un'ora.

#### I7 — Tre tranche, tre notifiche

`_notify_trade_opened` scatta a ogni trade. Con la scala riceveresti tre push
"trade aperto" per la stessa coin, più una per la chiusura.

**Soluzione:** notifica solo alla **prima tranche** (posizione aperta) e alla
chiusura. Le tranche 2 e 3 restano nel log e nel grafico, senza push.

#### I8 — Lo snapshot del grafico si appoggia a livelli che non esistono più

`_snapshot_closed_trade` usa `take_profit_1/2`, `stop_loss` e `stop_reference_time`
— tutti `None` nel nuovo modello. Oltre al payload (N16), va rivisto anche il
calcolo di `chart_start`, che oggi parte dal riferimento dello stop: dovrà partire
dal timestamp della **prima tranche**.

#### I9 — Motivi di chiusura nuovi

Le chiusure spot scrivono `notes = "auto_close:<reason>"`. I motivi nuovi
(`trend_break`, `rs_weakness`) non sono mappati in nessuna traduzione per la UI, e
`_close_purpose` (lato perp) non li conosce. Da aggiungere quando si tocca la UI.

#### I10 — Volume delle decisioni (nota positiva)

Oggi `_handle_signal` registra una `AgentDecision` per **ogni** asset a **ogni**
slow tick, anche per gli skip: molte righe al minuto. Col nuovo modello si valuta
solo alla chiusura di una candela 4h, quindi il volume cala di uno o due ordini di
grandezza. Va solo evitato che la passata giornaliera registri una decisione per
asset a ogni giro.

---

### 5.7 Stato della base di codice — ✅ RISOLTO (2026-08-31)

La suite aveva **15 test rossi già in HEAD** (11 in `test_agent_step6.py`, 3 nel
golden lifecycle, 1 nel support API), verificati su un worktree pulito del commit
`8dd41ac`. **Ora è verde: 384 passed, 2 skipped.**

| Gruppo | Causa reale | Rimedio |
|---|---|---|
| 4 × `market_reversal_filter_*` + 1 × `dry_run_persists` | il fixture `settings()` forniva solo la chiave generica `market_reversal_filter_enabled`, mentre il codice legge i campi per-mercato `spot_`/`perp_` che `config.py` deriva dalla stessa chiave YAML | il fixture ora deriva i due campi per-mercato |
| 1 × `dry_run_persists_decision_and_trade` | **bug di prodotto**: `_ms` non propagava `spot_max_stop_distance_filter_enabled` / `_pct`, quindi si usavano i default dello schema e `configs/strategy_spot.yaml` era **ignorato** per quei due parametri | i due campi ora vengono passati in `_ms` |
| 3 × trailing perp + 3 × golden lifecycle | le `PerpPosition` di test non impostavano `venue`, quindi `resolve_position_venue` non risolveva e la posizione non si chiudeva mai | aggiunto `venue="dry_run"` |
| 2 × golden lifecycle | i test descrivevano un **design mai implementato**: ratchet a chiusure parziali scalate (con un campo `ratchet_state` inesistente). Il Profit Lock reale è uno *stop che sale a gradini* e chiude tutto il residuo in un colpo, riempiendo al livello | test riallineati al design reale, con i valori economici esatti congelati |
| `test_meta_controller_reduce` | la banda `reduce` è stata **rimossa di proposito** in `1ddbf41` ("brain threshold alignment"), che ha anche portato la soglia di approvazione da 0.85 a 0.60 | riscritto come `test_meta_controller_local_fallback_bands`, che fissa le due bande attuali |
| `test_build_spot_swap_params_resolves_via_cmc` | il resolver CMC è stato **rimosso di proposito** in `2734ebb` ("remove CMC resolver"); il test è rimasto orfano | messo in `skip` con motivazione, in attesa di **Q1** |
| `test_support_ticket_thread_and_admin_status_flow` | **bug di prodotto**: confronto fra datetime naive (riletti da SQLite) e aware in `_ticket_summary` | normalizzazione a UTC prima del confronto |

**Due scoperte che riguardano direttamente Q1**: il resolver CMC non è "mai stato
collegato", è stato **rimosso deliberatamente** (`2734ebb`). Prima di ricablarlo va
capito perché fu tolto — il rischio noto è che un ticker mappi più token BEP20.

Nota di processo: durante questa sessione il repository ha ricevuto **modifiche
concorrenti** da fuori (perp/uscite, config, frontend). Chi esegue il piano dovrebbe
verificare `git status` prima di iniziare.

## 6. FASI DI LAVORO

| Fase | Contenuto | Dipendenze |
|---|---|---|
| **F0b** | **Sbloccare l'integrazione**: tetti di esposizione a 11%/90% in config **e** nell'override runtime (I2); fallback prezzi dal pool in `_refresh_position_prices` (I3); `price_source` nel payload (I5) | — |
| **F1** | **Mappa indirizzi BSC**: `configs/bsc_token_map.yaml`, quote token, script di verifica pool+liquidità. Fix B1/B3. | — |
| **F2** | **Universo automatico**: intersezione §4.2, esposta via API, con motivo di esclusione per ogni scarto | F1 |
| **F3** | **Storico daily**: backfill ≥ 250 candele daily per l'universo, con rate limiter e cache persistita | F2 |
| **F3b** | **Fonte OHLC del pool** per i token senza coppia Binance: integrazione, normalizzazione al formato `Candle`, pulizia delle mèche da singolo swap (S8) | F3 |
| **F4** | **Forza relativa**: implementare `relative_strength_v2.py`, percentili, isteresi 75/50, contatore dei 5 giorni; il segnale emette `quality = percentile/100` così il brain non scarta tutto (I1) | F3 |
| **F5** | **Rilevatore di regime**: BTC 100g + pendenza + % alt sopra 50g; on/off del motore | F3 |
| **F6** | **Spegnimento del vecchio motore**: C2-C8, **compresi i filtri di regime chiamati dentro `evaluate_spot`** e non nel modulo di segnale (I6); verifica V3-V7 | — (fattibile in parallelo) |
| **F6b** | **Schema DB**: colonne §5.6 con pattern `upgrade_schema`; sizing frazionato della 1ª tranche | F6 |
| **F7** | **Ingressi a scala**: riscrittura di `_maybe_scale_in_spot` con condizioni invertite (add contro, struttura integra), 3 tranche in ATR, annullamento su rottura 50g | F4, F5, F6b |
| **F7b** | **Stato della scala**: `ladder_state` (open/complete/cancelled/expired), scadenza N2, accorpamento tranche sotto la size minima N8 | F7 |
| **F8** | **Uscite strutturali**: priorità §4.5, **nessuno scarico parziale** (N13), **nessuna uscita da regime** (S18), rottura trend sospesa a scala aperta (N1), media 20g daily, debolezza RS | F7b |
| **F8b** | **Guardia di esecuzione**: divergenza Binance/PancakeSwap (N6), impatto sulla pool max 3% (N14) | F1, F8 |
| **F8c** | **`position_id` colonna vera su `SpotTrade`** (oggi il legame e' il prefisso del trade_id) + payload grafici a liste `entries[]`/`exits[]`, medie 50g/20g, marker; anche sul grafico live (N16) | F8 |
| **F9** | **Vincoli di portafoglio**: fetta spot separata (S19, I11), numero di posizioni adattivo al capitale (S20, N17), max 2 prime tranche/24h, ordinamento per ranking (V7) | F7 |
| ~~**F0**~~ | ~~Baseline verde~~ ✅ **FATTO (2026-08-31)**: suite a 384 passed / 2 skipped (§5.7) | — |
| **F9b** | **UI**: semaforo regime (e quale condizione manca), radar per percentile, motivo di esclusione, stato scala; parametri nuovi in `AgentMobileSettings` (N12); notifica solo alla 1ª tranche (I7); etichette per i motivi di chiusura nuovi (I9) | F9 |
| **F10** | **Dry-run** a size ridotta con **quote in ombra** (N15): verifica che i trigger scattino e misura divergenza/slippage/impatto pool senza eseguire. Priorità: N1 (l'ingresso non viene espulso subito) e N2 (quante scale restano incompiute) | tutte |
| **F11** | **Pulizia**: rimozione codice vecchio, aggiornamento `docs/Strategia_Spot.md` e `docs/Uscite_Spot.md`, memorie obsolete | F10 |

**F1 è bloccante per tutto il resto.** F6 può partire in parallelo perché è
sottrazione, non aggiunta.

---

## 7. CONFIGURAZIONE

Nuovo file `configs/strategy_spot_v2.yaml` (il vecchio resta finché non si rimuove
il motore precedente, per il rollback di Q4).

### Parametri nuovi

| Parametro | Default | Nota |
|---|---|---|
| `regime_btc_ema_on_days` | **20** | BTC sopra questa EMA daily: il motore puo' comprare |
| `regime_btc_ema_off_days` | **50** | BTC sotto questa EMA daily: il motore smette di comprare |
| `regime_alt_health_sma_days` | 50 | |
| `rs_lookback_days` | **14** | finestra forza relativa: le rotazioni crypto durano settimane, 30g arrivava tardi |
| `rs_enter_percentile` | 75 | |
| `rs_exit_percentile` | 50 | |
| `rs_exit_days` | 5 | giorni consecutivi sotto soglia |
| `asset_trend_sma_days` | 50 | media di struttura dell'asset |
| `exit_trend_sma_days` | 20 | media di uscita |
| `pullback_atr_trigger` | **1.0** | 1ª tranche: abbassato per far lavorare di piu' il motore |
| `ladder_atr_step` | 1.0 | distanza tranche successive |
| `ladder_fractions` | [0.50, 0.30, 0.20] | |
| `max_new_entries_per_day` | 2 | |
| `spot_equity_share_pct` | **40** | quota dell'equity tradabile gestita dallo spot (S19) |
| `min_tranche_usd` | **20** | soglia economica per tranche: sotto, il gas BSC pesa oltre l'1% (S20) |
| `max_positions` | 8 | tetto massimo; il numero effettivo lo decide il capitale (S20) |
| `first_tranche_fraction` | 0.50 | frazione del budget per asset alla 1ª tranche (vedi §4.4) |
| `ladder_expiry_bars` | 30 | scadenza della scala, candele 4h (N2) |
| `rs_min_universe` | 25 | sotto questa soglia si usa RS assoluta, non il percentile (N5) |
| `rs_absolute_enter` | 1.05 | soglia RS assoluta d'ingresso, universo piccolo (N5) |
| `rs_absolute_exit` | 0.95 | soglia RS assoluta d'uscita, universo piccolo (N5) |
| `max_price_divergence_pct` | 1.5 | scarto massimo prezzo Binance / quote PancakeSwap (N6) |
| `regime_alt_health_on_pct` | 45 | isteresi del regime: accende sopra 45% |
| `regime_alt_health_off_pct` | 35 | isteresi del regime: spegne sotto 35% |
| `max_pool_impact_pct` | 3.0 | quota massima delle riserve della pool per singola tranche (N14) |
| `shadow_quote_enabled` | true | in dry-run interroga PancakeSwap in sola lettura per misurare divergenza e slippage (N15) |

### Parametri esistenti da riusare (non duplicare)

| Nuovo concetto | Parametro esistente |
|---|---|
| Posizioni massime (8) | `ms.spot_max_open_positions` — da verificare il valore attuale |
| Peso per asset a scala piena | `ms.spot_capital_per_trade_pct` — **da 6% a 11%** (I2) |
| Soglia liquidità pool | `ms.min_pool_liquidity_usd` / `risk_min_pool_liquidity_usd` |
| Esposizione massima spot | `ms.spot_max_exposure_pct` — **da 30% a 90%**, altrimenti blocca alla 3ª posizione (I2) |

### Parametri che escono di scena

`confidence_threshold`, `volatility_trigger_pct`, `relative_volume_threshold`,
`atr_stop_multiplier`, `sl_mode`, `structural_stop_*`, `tp1_atr_multiplier`,
`tp2_atr_multiplier`, `tp1_close_fraction`, `breakeven_*`, `trailing_*`,
`scale_in_*`, `spike_filter_*`, `max_stop_distance_*`, `market_regime_filter_*`,
`market_reversal_filter_*`, tutti i pesi del quality score.

---

## 8. RISCHI

| Rischio | Mitigazione |
|---|---|
| La premessa di bull market non si avvera | L'interruttore §4.1 smette di comprare. **Attenzione**: da quando il regime non liquida piu' (S18), in un crollo rapido la protezione e' interamente affidata alle uscite per asset (media 20g, forza relativa). E' una scelta consapevole: evita di svuotare il portafoglio a ogni falso segnale, ma sposta il rischio sulla velocita' di quelle due uscite. Da tenere d'occhio in dry-run |
| L'universo si riduce troppo dopo i filtri (indirizzo + pool + liquidità + storico) | Misurare la dimensione dell'universo in F2 **prima** di costruirci sopra. Il vincolo Binance è caduto (S8), quindi il rischio è minore, ma resta il fallback a soglia assoluta di N5 se l'universo è comunque piccolo |
| Costi di esecuzione su DEX (LP fee + slippage + gas) erodono il vantaggio | Isteresi 75/50, max 2 ingressi/giorno, posizioni lunghe: pochi trade per costruzione |
| ~~Heartbeat giornaliero~~ | ✅ risolto (C8) |
| ~~Dedup/cooldown incrociati spot/perp~~ | ✅ risolti (V1, V2) |
| **Ingresso e uscita che si annullano (N1)** | Uscita trend su media 20g **daily** e solo a scala conclusa. È il rischio che renderebbe la strategia inoperante: da validare per primo in dry-run |
| **Sotto-investimento sui vincitori (N2)** | Scadenza della scala; misurare in dry-run quante scale restano incompiute |
| Divergenza prezzo Binance / pool BSC (N6) | Guardia `max_price_divergence_pct` prima di ogni esecuzione |
| Universo troppo piccolo per i percentili (N5) | Fallback a soglia assoluta sotto `rs_min_universe` |
| **Esecuzione non validata fino al mainnet (N15)** | Quote in ombra durante il dry-run: misura divergenza, slippage e impatto pool senza rischiare capitale. È l'unica verifica possibile prima di Q2 |
| Riavvio del bot che altera il comportamento (N11) | Stato in `runtime_state`, ripristino conservativo (`weak_days = 0`: mai un'uscita spuria) |
| **Capitale insufficiente per il disegno (N17)** | Dimensionamento adattivo: con l'equity attuale il motore aprira' 3 posizioni invece di 8, e salira' da solo quando il conto cresce. Da verificare in dry-run che il numero calcolato sia quello atteso |
| **Spot e perp che si affamano a vicenda (I11)** | Budget separati 40/60: ogni motore vede solo la propria fetta |
| Costi DEX superiori al movimento catturato (N13) | Eliminato lo scarico parziale: due swap in meno per posizione e bersagli molto piu' ampi, cosi' le fee tornano marginali |
| Nessuna validazione storica per scelta esplicita (S10) | Dry-run F10 con size ridotta; i parametri restano quelli argomentati, non ottimizzati |
| Rollback necessario | Q4: flag di selezione motore finché il nuovo non è validato |
| **Blocchi silenziosi da configurazione (I1, I2)** | Sono i più insidiosi: il bot non dà errore, semplicemente non compra. Vanno risolti in **F0b, prima di tutto il resto**, e verificati in dry-run contando le posizioni effettivamente aperte |
| **Posizioni bloccate senza prezzo (I3)** | Un token solo-DEX senza fallback sul prezzo non uscirebbe mai. Fallback obbligatorio in F0b, prima di ammettere token non-Binance nell'universo |

---

## 9. FUORI SCOPE

- Strategia **C delta-neutral** (funding farming): scheda separata futura.
- Motore **perp**: non toccato da questo piano.
- Passaggio a mainnet (Q2): decisione operativa separata.

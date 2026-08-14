# Report - Smart SL Rebuy TP Recovery

## COSA È STATO FATTO

- Analizzata la sequenza DOT Perp `pos_f3bea853d44142bc8fb5b5c82ca2d261` su `backend/local.db`.
- Corretto il ricalcolo dei Take Profit dopo Smart SL rebuy in `backend/app/agent/service.py`.
- Estesa la correzione sia al rebuy globale `smart_sl_rebuy_all` sia ai rebuy per livello `smart_sl_rebuy_l1/l2`.
- Aggiunto un test di regressione con i numeri del caso DOT e chiusura TP1 configurata al 70%.

## COME È STATO FATTO

- Il bug era nel calcolo precedente: distribuiva il target 40%/60% ma divideva entrambi i target per metà posizione, assumendo implicitamente uscite 50%/50%.
- La configurazione reale Perp usa `perp_tp1_close_pct = 70.0`, quindi i TP generati non coprivano la perdita Smart SL quando applicati dalla logica reale di chiusura.
- Il nuovo helper `_adjust_smart_sl_recovery_take_profits` calcola:
  - perdita Smart SL assoluta;
  - target netto = perdita * `(1 + recovery_delta_pct / 100)`;
  - target lordo di prezzo includendo fee/funding residui della posizione;
  - distanze TP usando la percentuale reale `perp_tp1_close_pct`.

## COSA È STATO VERIFICATO

- DB DOT verificato:
  - Smart SL sell L1: `-1.8139720055656172` USD.
  - Rebuy all: prezzo `0.7629`.
  - TP precedenti post-rebuy: `0.7630964382973082` e `0.7635696574461125`, troppo vicini per il target netto richiesto.
- Test mirato eseguito:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py::test_perp_smart_sl_rebuy_tp_adjustment_uses_actual_tp1_close_pct -q`
  - Esito: 1 passed.
- Suite Step 6 eseguita:
  - `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py -q`
  - Esito: 73 passed.

## SCOSTAMENTI DAL PIANO

- Nessuno rispetto alla richiesta: intervento correttivo mirato su runtime Perp Smart SL.

## QUESTIONI APERTE

- La posizione DOT storica resta già chiusa nel DB con i TP calcolati dalla vecchia formula; non è stata alterata retroattivamente.
- I prossimi rebuy useranno la nuova formula.

## STATO DELIVERABLE

- Deliverable completato: bug identificato, corretto e coperto da test di regressione.

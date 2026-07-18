# Report Trade Chart Close Alignment - 2026-07-18

## 1. COSA È STATO FATTO

- Corretto l'allineamento dei grafici trade chiusi quando vengono aggiunte candele post-close.
- Normalizzate le candele dello snapshot trade lato API prima della risposta.
- Allineati i renderer mobile app e dashboard alla candela reale di chiusura.
- Aggiunto un test di regressione per snapshot con candela successiva alla chiusura.

## 2. COME È STATO FATTO

- `backend/app/api/routes/views.py` ora ordina le candele dello snapshot e, per grafici non live, mantiene solo quelle con timestamp minore o uguale a `closed_at`.
- Il recupero delle candele post-close ora filtra rispetto al massimo tra `closed_at` e l'ultimo timestamp gia' presente nello snapshot normalizzato, evitando overlap.
- `src/components/AgentTab.tsx` e `dashboard/src/App.tsx` calcolano l'uscita come ultima candela con timestamp `<= closed_at`, poi disegnano la linea tratteggiata subito dopo quella candela.

## 3. COSA È STATO VERIFICATO

- Ispezionati i log backend recenti: nessun errore applicativo sul dettaglio trade, ma confermato il flusso `/api/v1/views/*` e klines.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py::test_closed_trade_chart_trims_snapshot_and_dedupes_post_close -q`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py -q`
- `npm run build`
- `npm run dashboard:build`

## 4. SCOSTAMENTI DAL PIANO

- Nessuno. La correzione e' rimasta confinata a dettaglio trade, grafici UI e test.

## 5. QUESTIONI APERTE

- Verificare visivamente su un trade reale gia' chiuso che la linea tratteggiata cada dopo la candela di uscita attesa.

## 6. STATO DELIVERABLE

- Deliverable implementato e verificato localmente.

# Report - Dashboard Tailscale Failed To Fetch

## COSA È STATO FATTO

- Diagnosticato il problema di accesso dati dashboard via Tailscale.
- Verificati processi, porte in ascolto, endpoint health e log backend recenti.
- Fermati due processi backend uvicorn in stato non valido.
- Riavviato il backend su `0.0.0.0:8001`.

## COME È STATO FATTO

- Controllata la porta dashboard `5176`, risultata correttamente in ascolto su `0.0.0.0`.
- Rilevato che il backend non esponeva più la porta `8001` nonostante processi Python/uvicorn ancora presenti.
- Dai log è emerso `WinError 64` sull'accept socket `0.0.0.0:8001`, coerente con backend rimasto vivo ma socket HTTP non più operativo dopo disconnessione/rete Tailscale.
- Riavviato il backend con:
  - `backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8001`

## COSA È STATO VERIFICATO

- `8001` in ascolto su `0.0.0.0`.
- `5176` in ascolto su `0.0.0.0`.
- `http://127.0.0.1:8001/health/live` risponde `200`.
- `http://100.66.71.112:8001/health/live` risponde `200`.
- Log dashboard/API dopo il riavvio:
  - richieste da `100.68.70.67` verso `/api/v1/views/spot`, `/api/v1/views/perp`, `/api/v1/views/global`, `/api/v1/views/equity-curve`, `/api/v1/agent/status` e health completate con `200`.

## SCOSTAMENTI DAL PIANO

- Nessuna modifica al codice applicativo.
- Intervento operativo runtime: restart backend locale.

## QUESTIONI APERTE

- Se il problema ricompare dopo sospensione PC o reconnect Tailscale, serve rendere il backend supervisionato/restartabile automaticamente invece di avviarlo come processo manuale.
- Se un browser continua a mostrare `Failed to fetch`, verificare che il campo Backend URL della dashboard non sia rimasto salvato su `127.0.0.1` o `localhost`; via Tailscale deve puntare a `http://100.66.71.112:8001`.

## STATO DELIVERABLE

- Connettività dashboard/backend ripristinata.

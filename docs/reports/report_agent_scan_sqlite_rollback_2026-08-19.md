# Report Agent Scan SQLite Rollback - 2026-08-19

## 1. COSA È STATO FATTO

- Diagnosticata la notifica FCM: `58/60 asset falliti nel ciclo di scansione - rolled back`.
- Corretto il loop lento dell'agente per eseguire `session.rollback()` dopo un errore di scan su singolo asset.
- Aumentato il timeout SQLite async a 30 secondi e applicati WAL/busy timeout a ogni nuova connessione async.
- Aggiunto un test di regressione che verifica che lo scanner continui con l'asset successivo dopo un errore DB per-asset.
- Aggiornato `docs/PROJECT_STRUCTURE.md`.

## 2. COME È STATO FATTO

- Dai log runtime `logs/backend.log` l'evento reale e' risultato:
  - timestamp `2026-08-19T09:45:18Z`;
  - evento `engine_health_degraded`;
  - `event_kind=storage_error`;
  - `scanned=60`, `failed=58`;
  - causa iniziale `sqlite3.OperationalError: database is locked` durante `INSERT INTO agent_decisions`.
- Il primo errore lasciava la `AsyncSession` in stato fallito; gli asset successivi ricevevano `This Session's transaction has been rolled back...`.
- In `backend/app/agent/service.py`, i blocchi `except` dello scanner Spot/Perp ora ripuliscono la sessione con rollback prima di procedere.
- In `backend/app/persistence/database.py`, SQLite async usa `connect_args={"timeout": 30}` e PRAGMA `journal_mode=WAL` / `busy_timeout=30000` anche sulle nuove connessioni.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py::test_slow_tick_rolls_back_after_asset_error_and_continues backend/tests/unit/test_agent_step6.py::test_agent_service_does_not_run_risk_universe_on_skipped_signal -q`: 2 passed.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_agent_step6.py::test_slow_tick_rolls_back_after_asset_error_and_continues -q`: 1 passed.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_persistence_layer.py::test_check_db_reports_connected_with_latency backend/tests/unit/test_persistence_layer.py::test_check_db_reports_disconnected_when_uninitialised -q`: 2 passed.
- `backend\.venv\Scripts\python.exe -c "from backend.app.agent.service import AgentService; from backend.app.main import app; print('backend imports ok')"`: import ok.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno step nuovo e' stato avviato.
- Non e' stata implementata una inbox dashboard dedicata agli alert agente: oggi questi eventi sono visibili nel Log Viewer admin solo se rientrano nel tail recente; l'endpoint log supporta filtro `search` per `engine_health_degraded` o `storage_error`, ma la UI non espone ancora una ricerca dedicata.

## 5. QUESTIONI APERTE

- La suite completa `backend/tests/unit/test_agent_step6.py` resta non green per failure preesistenti/non correlate: aspettative legacy sul meta-controller, attributi legacy del filtro reversal, resolver token e chiusure Perp venue.
- Per vedere gli alert agente fuori dal tail dei log serve una piccola estensione futura: persistenza degli eventi critici agente e pannello dedicato in dashboard/mobile.
- Se il lock SQLite continua in produzione, il passo successivo tecnico e' ridurre ulteriormente le scritture nel ciclo di scan o serializzare le scritture agente con una coda dedicata.

## 6. STATO DELIVERABLE

Parziale ma operativo: la causa della cascata `rolled back` e' mitigata e coperta da test mirato. La visibilita' dashboard resta limitata al Log Viewer/tail dei log, non a una inbox alert dedicata.

# Report Dashboard Log Filters - 2026-08-19

## 1. COSA È STATO FATTO

- Migliorato il Log Viewer della dashboard.
- Aggiunti filtri per priorita': actionable, critical, error, warning, info, all.
- Aggiunti filtri per categoria operativa: agent, storage, risk, execution, notifications, market data, API, support.
- Aggiunti conteggi sintetici per critical/error/warning/info.
- Aggiunta ricerca testuale e selettore limite righe.
- Evidenziati gli eventi critici come `engine_health_degraded`, `storage_error`, `database is locked` e `rolled back`.
- Il parser backend dei log ora usa `component` come sorgente quando presente.

## 2. COME È STATO FATTO

- In `dashboard/src/App.tsx` e' stato aggiunto uno stato `LogFilters`.
- Ogni log viene classificato lato client in priorita', categoria e azione suggerita.
- La vista di default mostra gli eventi actionable, quindi nasconde il rumore informativo finche' non viene richiesto.
- In `dashboard/src/styles.css` sono stati aggiunti layout e colori distinti per critical/error/warning.
- In `backend/app/api/routes/observability.py` la sorgente visualizzata preferisce il campo strutturato `component`.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_observability_logs.py -q`: 2 passed.
- `npm run dashboard:build`: completato correttamente.
- Un tentativo precedente con comando build errato (`npm run build -- --config dashboard/vite.config.ts`) e' fallito per entry Vite non risolta; non e' un errore del codice.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno step nuovo e' stato avviato.
- Non e' stata implementata persistenza separata degli alert agente: il miglioramento riguarda lettura e interpretazione dei log esistenti.

## 5. QUESTIONI APERTE

- Per non dipendere dal tail dei log serve una inbox persistente degli eventi critici agente, alimentata al momento dell'invio FCM.
- La UI usa classificazione euristica lato client; se i log cresceranno, conviene spostare priorita'/categoria nel backend come campi strutturati.

## 6. STATO DELIVERABLE

Completato per il bisogno immediato: il Log Viewer non e' piu' un elenco grezzo e rende visibili per prime le condizioni operative che bloccano l'agente.

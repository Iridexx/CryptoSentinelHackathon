# Piano · Notifiche dashboard (toast + pagina dedicata)

## Decisioni prese (Q&A)

| Tema | Scelta |
|---|---|
| Sorgente | **Feed backend persistente** (nuova tabella + endpoint); l'AgentNotifier scrive ogni evento nel feed oltre che via FCM |
| Aggiornamento real-time | **Polling corto** — `GET /feed?since=<cursor>` ogni ~10s. Niente SSE, niente cookie. Stessa auth (read token nell'header) di tutte le altre chiamate |
| Cosa fa toast | **Configurabile per categoria** (flag `toast_*`), default = solo critici + trade |
| Stato letto/non letto | **Server-side, singolo stato condiviso** (`read_at` sulla riga) |
| Retention | **30 giorni + max 2000 righe**, prune automatico |
| UX toast | Stack top-right, 5s (7s critici), pausa su hover, progress bar, **suono sui critici + badge conteggio nel `<title>`**, toggle Do-Not-Disturb |
| Pagina Notifiche | **Timeline unica**, raggruppata per giorno, barra filtri (categoria / severità / solo non letti / ricerca) |
| Supporto | **Resta separato** (meccanismo attuale `supportNotifications`) |
| Permessi | Feed, `segna letto`, `toast-prefs` tutti sotto **read token** (header, come il resto) |
| Flag toast per categoria | **Nuovo endpoint read separato** `GET/PUT /notifications/toast-prefs` (non tocca `notification_prefs` admin) |
| Apertura pagina Notifiche | **Non** auto-segna letto: il badge cala solo su click riga o "Segna tutte" |

> Nota sul polling: latenza tipica del toast ~10s. Accettabile per una dashboard operativa (gli eventi sono rari, il resto della UI aggiorna ogni 45s). Se in futuro serve il push istantaneo → fase 9 opzionale con `fetch()` in streaming (`@microsoft/fetch-event-source`), che mantiene l'auth via header e non richiede cookie: cambia solo *come* il frontend consuma lo stream, il resto resta.

## Categorie evento

`spot_trade` · `perp_trade` · `risk` · `reserve` · `system` (agente critico) · `summary` (riepilogo giornaliero)

Severità: `info` · `normal` · `critical`.

Default flag toast: `toast_spot_trade`, `toast_perp_trade`, `toast_risk`, `toast_system` = `true`; `toast_reserve`, `toast_summary` = `false`.
Distinzione: la categoria base (es. `spot_trades` in `NotificationPreferences`) decide se l'evento **entra nel feed**; il flag `toast_*` decide se **compare come toast**.

---

## Backend

### 1. Modello `NotificationEvent` — `persistence/models/notifications.py`
- `id` PK · `event_id` str uuid unique index
- `user_id` index
- `category` str · `severity` str
- `title` str · `body` text
- `data_json` JSON (payload originale: trade_id, prezzi, close_reason, alert_type…)
- `link_type` / `link_ref` nullable (click-through, es. `trade` / `spot:<id>`)
- `created_at` tz index · `read_at` tz nullable
- Registrare in `models/__init__.py` → `create_all` crea la tabella (no Alembic, coerente col resto).

### 2. Repository — `persistence/repositories/notifications.py`
- `append(...) -> NotificationEvent`
- `list(since=None, before=None, categories=None, severities=None, unread_only=False, q=None, limit=100)` — cursor = `(created_at, id)` serializzato in `event_id`
  - `since=<cursor>` → solo eventi **più recenti** del cursore, ordine crescente (uso del polling)
  - `before=<cursor>` → pagina indietro nello storico, ordine decrescente (uso della timeline "Carica altre")
- `mark_read(ids=None, all=False, before=None) -> int` (nuovo unread_count)
- `unread_count() -> int`
- `prune()` — elimina `created_at < now-30g`, poi se `count > 2000` elimina le più vecchie oltre 2000

### 3. Integrazione `AgentNotifier`
- Nuovo `_record(user_id, category, severity, title, body, data, link=None)`: scrive nel repo + `prune()` ogni ~20 append.
- Ogni `_send(...)` FCM esistente chiama anche `_record(...)`, riusando l'idempotenza già presente (`_add_notified`).
- Popolato anche con FCM disabilitato (dev / dry-run).
- Nessun broadcast in-process: il feed vive solo sul DB, il frontend lo interroga a intervalli.

### 4. Endpoint — `api/routes/notifications.py` (prefix esistente `/api/v1/notifications`)
- `GET /feed` (read) → `{ items, unread_count, cursor }`; params `since`, `before`, `categories`, `severities`, `unread_only`, `q`, `limit`
- `POST /feed/read` (read) → body `{ ids: [...] }` | `{ all: true, before?: cursor }` → `{ unread_count }`
- `GET/PUT /notifications/toast-prefs` (read) → i 6 flag `toast_*` (stato condiviso; persistenza su riga `runtime_state` `toast_preferences` o mini-tabella). `notification_prefs` (admin) resta intatto.

Tutti e tre usano l'auth header esistente (`ReadAccessDep`). Nessuna modifica a CORS, cookie, HTTPS.

---

## Frontend (dashboard)

### 1. `dashboard/src/notifications.ts` — hook `useNotifications(session, toastPrefs, dnd)`
- fetch iniziale `GET /feed?limit=50` → popola `items`, `unreadCount`, salva `cursor`
- `setInterval` ogni **10s**: `GET /feed?since=<cursor>` → se torna roba nuova, per ogni evento (dal più vecchio al più recente):
  - prepend a `items` (tieni ~50 in memoria), aggiorna `cursor`, `unreadCount++`
  - se `toastPrefs['toast_'+category]` e non `dnd` → push in coda toast
  - se `severity === 'critical'` e non `dnd` → beep WebAudio + aggiorna `document.title`
- pausa il polling quando `document.hidden` è true; alla riattivazione fa subito un giro
- gestione errori: un giro fallito non fa nulla, ci riprova al successivo (nessun backoff da gestire)
- `markRead(ids)` / `markAllRead()` → `POST /feed/read`, aggiorna `unreadCount` dalla risposta

### 2. `<ToastHost>` — portale fisso top-right
- stack max 4; `aria-live` polite (critici assertive)
- card: bordo-sx per severità (info grigio · normal blu · critical rosso), icona categoria, titolo, body, `×`, progress bar CSS
- 5s / 7s critici; hover = pausa (`animation-play-state` + reset timeout); critici = niente auto-dismiss
- click corpo → naviga alla tab collegata + segna letto
- entrata slide+fade 150ms; `prefers-reduced-motion` → solo fade

### 3. Do Not Disturb
- toggle in cima alla pagina Notifiche, persistito in `localStorage` `cs.dashboard.dnd`; blocca toast + suono + title badge; il feed continua ad aggiornarsi

### 4. Suono + title badge
- beep sintetico WebAudio (~120ms, 2 note) solo su `critical` + non DND
- `document.title = unread ? \`(\${unread}) CryptoSentinel\` : 'CryptoSentinel · Judge Dashboard'`

### 5. Sidebar
- nuova voce `tabs`: `{ id: 'notifications', label: 'Notifiche' }`, posizionata sotto **Overview**
- badge conteggio non letti sul bottone (pallino rosso + numero)

### 6. `<NotificationsPanel>`
- **Header**: "Segna tutte come lette" · toggle DND · "Impostazioni toast" (pannellino coi 6 switch, salva su `PUT /toast-prefs`) · indicatore "aggiornato Xs fa"
- **Filtri**: chip categoria multi-select · select severità · checkbox "solo non letti" · ricerca (debounce; `q` all'endpoint per storico)
- **Timeline**: heading giorno sticky ("Oggi" / "Ieri" / data); riga = icona categoria colorata + titolo + body (2 righe) + ora relativa (assoluta in hover) + pallino non-letto; click → segna letto + eventuale click-through
- **Paginazione**: "Carica altre" → `GET /feed?before=<cursor>`
- **Empty state** dedicato
- All'apertura **non** si auto-segna tutto letto (diverso da Support): il badge cala solo su click riga o "Segna tutte come lette".

---

## File toccati (stima)
**Backend**: `models/notifications.py` (nuovo) · `models/__init__.py` · `repositories/notifications.py` (nuovo) · `notifications/agent_notifier.py` · `api/routes/notifications.py` · `schemas/notifications.py` · test unit + integration
**Frontend**: `dashboard/src/api.ts` · `types.ts` · `notifications.ts` (nuovo) · `App.tsx` · CSS

## Ordine di implementazione
1. Modello + repo (`append`, `list` con `since`/`before`, `mark_read`, `unread_count`, `prune`) + test
2. `_record` in `AgentNotifier`, agganciato a ogni `_send` + test
3. Endpoint `GET /feed`, `POST /feed/read`, `GET/PUT /toast-prefs` + test integration
4. Frontend: client `api.ts` + hook `useNotifications` (fetch iniziale + polling 10s + pausa su tab nascosta)
5. `<ToastHost>` + suono + title badge + DND
6. `<NotificationsPanel>` + voce sidebar con badge non letti
7. Rifinitura UX (animazioni, `prefers-reduced-motion`, heading sticky) + report

## Fase 9 opzionale (solo se un domani serve il push istantaneo)
Sostituire il polling con `fetch()` in streaming lato frontend (`@microsoft/fetch-event-source`) + endpoint `GET /feed/stream` che tiene la risposta aperta. Auth sempre via header, nessun cookie. Il resto del sistema non cambia.

## Stato
Tutte le decisioni sono chiuse. Nessun punto aperto lato infrastruttura. Pronto per la fase 1.

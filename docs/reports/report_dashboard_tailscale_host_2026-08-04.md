# Report Dashboard Tailscale Host - 2026-08-04

## 1. COSA E STATO FATTO

La dashboard Vite e stata configurata per ascoltare su tutte le interfacce di rete invece che solo su `127.0.0.1`.

Gli script Windows di avvio e riavvio mostrano sia l'URL locale sia l'URL Tailscale quando viene rilevato un indirizzo `100.x.y.z`.

Il backend accetta anche l'origin CORS della dashboard servita via Tailscale sulla porta dashboard configurata.

## 2. COME E STATO FATTO

Gli script npm `dashboard:dev` e `dashboard:preview` usano `--host 0.0.0.0`. La configurazione `dashboard/vite.config.ts` imposta `server.host` e `preview.host` a `0.0.0.0`.

Gli script PowerShell leggono l'IPv4 dell'interfaccia Tailscale e stampano l'indirizzo da usare dagli altri dispositivi.

Il middleware CORS FastAPI usa un regex ristretto a `localhost`, `127.0.0.1` e IP Tailscale `100.x.y.z` sulla porta `dashboard_port`, evitando wildcard globali.

## 3. COSA E STATO VERIFICATO

E stato verificato che il processo dashboard precedente era in ascolto solo su `127.0.0.1:5176` e che l'IP Tailscale locale rilevato era `100.66.71.112`.

E stato verificato che il backend era raggiungibile via Tailscale ma rifiutava il preflight CORS con `Disallowed CORS origin`, causa del `Failed to fetch` nel browser remoto.

## 4. SCOSTAMENTI DAL PIANO

Nessuno.

## 5. QUESTIONI APERTE

Per chiamare il backend da altri dispositivi, la dashboard deve usare come backend URL l'indirizzo Tailscale della macchina backend.

## 6. STATO DELIVERABLE

Implementato a livello configurazione/script/backend CORS. Serve riavviare backend e dashboard per applicare tutto nel runtime gia avviato.

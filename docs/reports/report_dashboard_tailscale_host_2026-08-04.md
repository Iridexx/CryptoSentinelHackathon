# Report Dashboard Tailscale Host - 2026-08-04

## 1. COSA È STATO FATTO

La dashboard Vite è stata configurata per ascoltare su tutte le interfacce di rete invece che solo su `127.0.0.1`.

Gli script Windows di avvio e riavvio ora mostrano sia l'URL locale sia l'URL Tailscale quando viene rilevato un indirizzo `100.x.y.z`.

## 2. COME È STATO FATTO

Gli script npm `dashboard:dev` e `dashboard:preview` usano `--host 0.0.0.0`. La configurazione `dashboard/vite.config.ts` imposta `server.host` e `preview.host` a `0.0.0.0`.

Gli script PowerShell leggono l'IPv4 dell'interfaccia Tailscale e stampano l'indirizzo da usare dagli altri dispositivi.

## 3. COSA È STATO VERIFICATO

È stato verificato che il processo dashboard precedente era in ascolto solo su `127.0.0.1:5176` e che l'IP Tailscale locale rilevato è `100.66.71.112`.

## 4. SCOSTAMENTI DAL PIANO

Nessuno.

## 5. QUESTIONI APERTE

Per chiamare il backend da altri dispositivi, la dashboard deve usare come backend URL l'indirizzo Tailscale della macchina backend e il CORS backend deve includere l'origin dashboard Tailscale nel file locale `configs/instance.yaml`.

## 6. STATO DELIVERABLE

Implementato a livello configurazione/script. Serve riavviare la dashboard per applicare il nuovo bind.

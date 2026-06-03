# CryptoSentinel — Market Watch

**CryptoSentinel** è un'app Android per monitorare i prezzi delle criptovalute in tempo reale e ricevere notifiche personalizzate quando il mercato si muove.

---

## Funzionalità principali

### Monitoraggio prezzi
- Lista aggiornabile delle top criptovalute per capitalizzazione (fino a 600)
- Prezzi in tempo reale tramite API CoinGecko (polling configurabile da 5s a 5min)
- Supporto multi-valuta: USD, EUR e BTC
- Ricerca rapida per nome o simbolo
- Pull-to-refresh manuale

### Grafici
- Grafico a linea e a candele per ogni coin
- Timeframe selezionabile: 1 giorno, 7 giorni, 30 giorni, 1 anno
- Linee di soglia degli alert sovrapposte al grafico
- Si apre toccando il nome della coin, si chiude scorrendo verso il basso

### Alert di prezzo
- **Soglia fissa** — notifica quando il prezzo supera o scende sotto un valore
- **Variazione percentuale** — notifica su variazione % rispetto al prezzo attuale
- **Range** — notifica quando il prezzo entra o esce da un intervallo definito
- Note personalizzate su ogni alert
- Toggle per attivare/disattivare singoli alert senza cancellarli
- Storico degli ultimi 50 alert scattati

### Preferiti
- Aggiunta di coin ai preferiti con monitoraggio separato
- Alert di movimento percentuale sui preferiti (rialzo e ribasso configurabili)
- Popup di notifica in-app al rilevamento del movimento

### Notifiche
- Notifiche native Android anche con app chiusa o in background
- Worker in background (WorkManager, ogni 15 minuti) per i controlli prezzi
- Ripristino automatico del worker dopo il riavvio del dispositivo
- Canale notifiche dedicato con vibrazione e suono

### Altro
- Schermata di benvenuto animata all'avvio (solo al cold start)
- Aggiornamenti in-app scaricabili direttamente dall'app
- Supporto per l'ottimizzazione batteria con accesso diretto alle impostazioni Android

---

## Stack tecnologico

| Livello | Tecnologia |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Stile | Tailwind CSS |
| Grafici | TradingView Lightweight Charts v5 |
| Mobile | Capacitor 8 (Android) |
| Background | Android WorkManager |
| Notifiche | Capacitor Local Notifications |
| Dati | CoinGecko API (free tier) |

---

## Requisiti

- **Android** 7.0+ (API 24)
- Compilato con SDK 36 (Android 16)
- Nessun backend proprio — i dati vengono da CoinGecko

---

## Build locale

### Prerequisiti
- Node.js 18+
- Android Studio con SDK 36
- Java 17+

### Comandi

```bash
# Installa le dipendenze
npm install

# Build web
npm run build

# Sincronizza con il progetto Android
npx cap sync android

# Apri in Android Studio
npx cap open android
```

Per il dev server web (senza Android):
```bash
npm run dev
```

---

## Struttura del progetto

```
src/
├── components/        # Componenti UI React
│   ├── CoinCard       # Card singola coin con prezzo e variazioni
│   ├── CoinChartSheet # Bottom sheet con grafico e alert della coin
│   ├── AlertModal     # Modale creazione/modifica alert
│   ├── AlertsTab      # Lista di tutti gli alert attivi e storico
│   ├── SplashOverlay  # Schermata di avvio animata
│   └── ...
├── hooks/             # Custom hooks
│   ├── useCryptoData  # Fetch e polling prezzi da CoinGecko
│   ├── useCoinChart   # Fetch dati storici per il grafico
│   ├── useAlerts      # Gestione alert di soglia
│   ├── useRangeAlerts # Gestione alert di range
│   └── useFavoritePriceAlerts  # Alert movimento sui preferiti
└── utils/
    ├── notifications  # Invio notifiche native via Capacitor
    └── update         # Comunicazione con il plugin nativo AppSettings

android/app/src/main/java/com/cryptosentinel/app/
├── MainActivity.java       # Entry point, registra il plugin e avvia il worker
├── PriceCheckWorker.java   # WorkManager: controlla prezzi e invia notifiche
├── AppSettingsPlugin.java  # Plugin Capacitor per funzionalità native
└── BootReceiver.java       # Ripristina il worker dopo riavvio dispositivo
```

---

## Note sull'API

L'app usa il **tier gratuito di CoinGecko**, che ha un limite di richieste per minuto. Se si usa un intervallo di aggiornamento basso (es. 5s) con molte coin monitorate, si può incappare nel rate limit. In quel caso l'app riprova silenziosamente senza mostrare errori, purché ci siano dati in cache.

---

## Supporta il progetto

CryptoSentinel è gratuito e senza pubblicità. Se lo trovi utile puoi offrire un caffè ☕

| Metodo | Indirizzo |
|---|---|
| ☕ Buy Me a Coffee | [buymeacoffee.com/eifel3btc](https://buymeacoffee.com/eifel3btc) |
| ⚡ Lightning Network | [eifel@getalby.com](https://getalby.com/p/eifel) |
| ₿ Bitcoin (on-chain · Taproot) | `bc1pfzyjm5759qv0rjfsxld4jcejqv7elkuw6j9w2dxcsyrdf4vsw6yq6lexdg` |
| 💎 USDT / USDC (EVM) | `0x80f8Fc375bCf1a7BC38394d6048e8364628Bd6C0` |

> L'indirizzo EVM è compatibile con Ethereum, Polygon, BNB Chain, Arbitrum e qualsiasi altra rete EVM.

---

## Licenza

Uso personale. Non affiliato con CoinGecko.

# PROJECT STRUCTURE

Ultimo aggiornamento: 2026-06-13

Documento di riferimento per revisione esterna. Viene aggiornato al termine di ogni step operativo.

## 1. STRUTTURA CARTELLE

```text
CryptoSentinelHackathon/ - repository CryptoSentinel + backend agente BNB Hack Track 1.
|-- AGENTS.md - regole operative permanenti per agenti AI sul repository.
|-- .github/ - automazioni CI/CD GitHub.
|   `-- workflows/build-apk.yml - workflow GitHub Actions per build APK debug con JDK 21, restore sicuro google-services da secret, artifact prima delle release e deploy Pages su gh-pages solo da main.
|-- android/ - progetto Android Capacitor esistente.
|   |-- app/ - modulo Android principale.
|   |   |-- src/main/AndroidManifest.xml - dichiarazioni activity, provider, permessi e FCM.
|   |   |-- src/main/java/com/cryptosentinelai/app/ - codice nativo Java.
|   |   |   |-- MainActivity.java - entrypoint Android e registrazione plugin custom.
|   |   |   `-- AppSettingsPlugin.java - bridge Capacitor per impostazioni e download APK.
|   |   |-- src/main/res/ - risorse Android: icone, splash, layout, stringhe, stili e XML provider.
|   |   |-- src/test/ - test JVM Android di esempio.
|   |   |-- src/androidTest/ - test strumentali Android di esempio.
|   |   |-- build.gradle - build modulo Android, signing debug e versione da buildNumber.
|   |   |-- capacitor.build.gradle - dipendenze plugin Capacitor, incluso push notifications.
|   |   |-- debug.keystore - keystore debug Android.
|   |   `-- proguard-rules.pro - regole ProGuard/R8.
|   |-- capacitor.settings.gradle - include moduli Capacitor.
|   |-- gradle/wrapper/ - Gradle wrapper.
|   |-- build.gradle - build root Android e Google Services plugin.
|   |-- gradle.properties - proprietà Gradle.
|   |-- gradlew / gradlew.bat - wrapper Gradle Unix/Windows.
|   |-- settings.gradle - configurazione moduli Gradle.
|   `-- variables.gradle - versioni SDK/librerie Android.
|-- backend/ - backend FastAPI/Python per agente autonomo.
|   |-- __init__.py - namespace backend.
|   |-- README.md - runbook backend, endpoint, auth, configurazione e FCM.
|   |-- requirements.txt - dipendenze Python backend, incluso PyYAML per config centralizzata.
|   |-- app/ - package applicativo backend.
|   |   |-- main.py - entrypoint FastAPI, lifespan, heartbeat loop, CORS, proxy headers, logging richieste.
|   |   |-- api/ - router FastAPI e dipendenze API.
|   |   |   |-- dependencies.py - dipendenze read/admin/device token e Settings.
|   |   |   `-- routes/ - route FastAPI.
|   |   |       |-- __init__.py - aggrega router health/status/admin/notifications/alerts/market data.
|   |   |       |-- alerts.py - sincronizzazione configurazione alert e pending badge preferiti con acknowledgement.
|   |   |       |-- admin.py - endpoint admin manual heartbeat.
|   |   |       |-- health.py - liveness/readiness/heartbeat con stato notifiche e DB not_checked fino Step 5.
|   |   |       |-- notifications.py - registrazione token device, status FCM e invio admin push.
|   |   |       |-- market_data.py - endpoint normalizzati markets/prices/search/OHLCV e selettore globale admin-only.
|   |   |       `-- status.py - status backend autenticato.
|   |   |-- agent/ - agent autonomous trading.
|   |   |   |-- heartbeat.py - heartbeat interno in memoria.
|   |   |   |-- brain/ - namespace Claude/meta-controller futuro.
|   |   |   |-- loops/ - namespace loop veloce/lento futuri.
|   |   |   |-- risk/ - namespace risk engine e guardrail futuri.
|   |   |   `-- signals/ - signal engine modulare Spot/Perp/V2.
|   |   |       |-- base.py - primitive base signal engine.
|   |   |       |-- spot/momentum.py - placeholder momentum Spot.
|   |   |       |-- spot/relative_strength_v2.py - placeholder relative strength V2.
|   |   |       |-- perp/volume_profile.py - placeholder Volume Profile Perp.
|   |   |       `-- perp/orderflow_delta_v2.py - placeholder order-flow delta V2.
|   |   |-- core/ - configurazione, logging e sicurezza.
|   |   |   |-- config.py - unico loader Settings: fonde .env + configs/*.yaml, valida guardrail hard.
|   |   |   |-- logging.py - structlog JSON/console con file giornaliero rotante e retention configurabile.
|   |   |   `-- security/ - sicurezza API/custody.
|   |   |       |-- auth.py - autenticazione token read/device/admin fail-closed.
|   |   |       |-- headers.py - security headers e HSTS condizionale.
|   |   |       `-- wallet_custody.py - regola chiavi private solo cifrate e mai in chiaro.
|   |   |-- data/ - integrazioni dati mercato.
|   |   |   |-- market_data/ - astrazione multi-provider Step 3.
|   |   |   |   |-- base.py - interfaccia MarketDataProvider, identità asset e modelli normalizzati.
|   |   |   |   |-- aliases.py - mapping ID storico app/CoinGecko verso slug CMC.
|   |   |   |   |-- registry.py - selettore globale e riconciliazione ID storici resiliente: conserva i risultati CMC se il catalogo identità è indisponibile.
|   |   |   |   |-- cmc.py - adapter CMC REST con liste a blocchi da 200, ricerca progressiva e risoluzione preferiti per simbolo/ID.
|   |   |   |   |-- coingecko.py - adapter CoinGecko secondario e catalogo identità degli ID storici con cache giornaliera.
|   |   |   |   |-- http.py - client condiviso con cache, rate limiting e contatore crediti.
|   |   |   |   |-- cache.py / rate_limit.py / credits.py - primitive TTL, throttling e budget CMC.
|   |   |   `-- mcp/cmc.py - metadata connessione MCP ufficiale CMC senza esposizione chiavi.
|   |   |-- domain/ - modelli dominio separati: common, spot, perp, global_state.
|   |   |-- execution/ - adapter esecuzione futuri: spot_twak, perp_bnb_sdk, wallet, x402.
|   |   |-- i18n/locales/ - traduzioni backend en.json e it.json, incluse chiavi market data Step 3.
|   |   |-- notifications/ - sistema notifiche server-side.
|   |   |   |-- alert_store.py - persistenza JSON configurazione, stato checker e badge preferiti pendenti fino allo Step 5.
|   |   |   |-- price_checker.py - controllo prezzi ogni 60 secondi tramite MarketDataProvider e invio alert FCM.
|   |   |   |-- service.py - orchestration registry + FCM client.
|   |   |   `-- fcm/ - integrazione Firebase Cloud Messaging.
|   |   |       |-- client.py - wrapper Firebase Admin SDK, delivery e skipped se non configurato.
|   |   |       `-- token_store.py - registro token FCM persistente su JSON fino allo Step 5.
|   |   |-- observability/ - namespace metriche, health, replay/export futuri.
|   |   |-- persistence/ - migrazioni, modelli DB e repository futuri.
|   |   |-- schemas/ - schemi API.
|   |   |   |-- alerts.py - payload sincronizzazione soglie, range e preferiti.
|   |   |   |-- notifications.py - device token, notification request/response e status.
|   |   |   `-- market_data.py - response API normalizzate e selezione provider.
|   |   |-- services/ - namespace application services.
|   |   `-- tasks/ - namespace scheduled/background tasks.
|   |-- scripts/ - script di avvio backend.
|   |   |-- run_backend.ps1 - avvio Windows PowerShell (dev/prod, legge host:port da Settings).
|   |   `-- run_backend.sh  - avvio Linux/bash per VPS (dev/prod, stesso comportamento).
|   `-- tests/ - test backend.
|       |-- unit/test_alert_store.py - regressione stato alert tra sincronizzazioni.
|       |-- unit/test_auth_scopes.py - separazione scope device, alerts e admin.
|       |-- unit/test_market_data_rate_limit.py - accodamento richieste oltre soglia.
|       `-- integration/ - gate Step 3: provider, normalizzazione, cache crediti, API, smoke reali.
|-- configs/ - configurazione versionata e template installazione.
|   |-- README.md - categorie config, precedenza e guardrail hard.
|   |-- instance.example.yaml - template installazione non segreta; copiare in instance.yaml locale gitignored.
|   |-- risk.yaml - default funzionali risk management e guardrail prudenziali.
|   |-- strategy_spot.yaml - default strategia Spot.
|   |-- strategy_perp.yaml - default strategia Perpetual.
|   `-- eligible_tokens.yaml - universo 149 token eligible da piano.
|-- docs/ - documentazione progetto e review.
|   |-- CURRENT_STRUCTURE.md - baseline pre-integrazione backend.
|   |-- PROJECT_STRUCTURE.md - questo documento aggiornato a ogni step.
|   |-- Strategia_Spot.md - strategia Spot.
|   |-- Strategia_Perpetual.md - strategia Perpetual.
|   |-- index.html - pagina documentale/statica.
|   `-- reports/ - report step.
|       |-- report_step0.md - report Step 0.
|       |-- report_step1.md - report Step 1.
|       |-- report_step2.md - report Step 2.
|       |-- report_step2_final.md - chiusura finale Step 2 dopo test reali e revisione commit.
|       |-- report_step3.md - report implementazione astrazione multi-provider e test-gate.
|       `-- report_config_refactor.md - report task intermedio ambiente/config.
|-- plans/ - piani operativi.
|   `-- Plan_forHackathon.md - piano completo BNB Hack Track 1.
|-- public/ - asset statici frontend/PWA.
|-- scripts/ - script frontend/tooling.
|   `-- gen-icons.mjs - generazione icone.
|-- src/ - frontend React/TypeScript esistente.
|   |-- components/ - componenti UI CryptoSentinel.
|   |-- hooks/ - hook dati, alert, preferiti, valuta, search e refresh.
|   |-- services/marketData.ts - client unico verso API backend con request ID e diagnostica non sensibile.
|   |-- utils/ - notifiche, update, haptics, audio, energy saving.
|   |   |-- alertSync.ts - sincronizzazione alert attivi verso il backend.
|   |   |-- marketDataDiagnostics.ts - buffer locale degli ultimi eventi market-data senza token.
|   |   `-- notifications.ts - registrazione token FCM e rendering locale push in foreground.
|   |-- App.tsx - root app mobile/web; sincronizza sempre l'intero insieme dei preferiti salvati.
|   |-- hooks/useFavoriteCoinsData.ts - recupero preferiti mancanti con retry rapido e righe temporanee per tutti gli ID salvati.
|   |-- hooks/useSearch.ts - ricerca debounced tramite endpoint backend e provider globale selezionato.
|   |-- index.css - CSS globale/Tailwind.
|   |-- main.tsx - entrypoint React.
|   |-- types.ts - tipi frontend.
|   `-- vite-env.d.ts - tipi Vite.
|-- .env.example - template solo segreti/sensitive paths, valori vuoti.
|-- .gitignore - esclusioni frontend, backend, segreti, instance config e storage locale.
|-- capacitor.config.ts - configurazione Capacitor.
|-- package.json - script e dipendenze frontend/mobile, incluso push notifications.
|-- package-lock.json - lockfile npm.
|-- README.md - documentazione app mobile esistente.
|-- requirements.txt - delega install Python a backend/requirements.txt.
`-- vite/ts/eslint/tailwind/postcss config files - configurazione frontend/tooling.
```

## 2. STACK TECNOLOGICO

### Frontend/mobile esistente

| Tecnologia | Versione | Scopo |
|---|---:|---|
| React | ^19.2.6 | UI frontend/mobile. |
| React DOM | ^19.2.6 | Rendering DOM. |
| TypeScript | ~6.0.2 | Tipizzazione frontend. |
| Vite | ^8.0.12 | Build e dev server frontend. Dashboard futura: porta richiesta 5176. |
| Tailwind CSS | ^3.4.19 | Styling UI. |
| Capacitor Core/Android/CLI | ^8.3.4 | Bridge e target Android. |
| Capacitor Haptics | ^8.0.2 | Feedback aptico. |
| Capacitor Local Notifications | ^8.2.0 | Notifiche locali Android mantenute come fallback. |
| Capacitor Push Notifications | ^8.1.1 | Registrazione token FCM lato mobile. |
| lightweight-charts | ^5.2.0 | Grafici prezzo. |
| qrcode | ^1.5.4 | Generazione QR code. |

### Backend Python

| Dipendenza | Versione | Scopo |
|---|---:|---|
| fastapi | 0.115.6 | Framework API backend. |
| uvicorn[standard] | 0.34.0 | ASGI server. |
| pydantic | 2.10.4 | Modelli e validazione dati. |
| pydantic-settings | 2.7.1 | Settings da ambiente con precedenza controllata. |
| python-dotenv | 1.0.1 | Caricamento .env locale a runtime. |
| PyYAML | 6.0.3 | Parsing YAML per configs/*.yaml. |
| sqlalchemy | 2.0.36 | ORM/persistenza futura. |
| alembic | 1.14.0 | Migrazioni database future. |
| aiosqlite | 0.20.0 | Driver SQLite async iniziale. |
| psycopg[binary] | 3.2.3 | Driver PostgreSQL per VPS. |
| httpx | 0.28.1 | Client HTTP async per adapter CMC/CoinGecko e integrazioni esterne. |
| web3 | 7.6.1 | Interazioni BSC/on-chain future. |
| cryptography | 44.0.0 | Cifratura key material e sicurezza. |
| firebase-admin | 7.4.0 | Invio notifiche FCM server-side. |
| structlog | 24.4.0 | Logging strutturato. |
| python-json-logger | 3.2.1 | Log JSON. |
| pytest | 8.3.4 | Test backend. |
| pytest-asyncio | 0.25.0 | Test async. |
| ruff | 0.8.4 | Lint/format Python. |

### Android/CI

| Componente | Versione/config | Scopo |
|---|---:|---|
| minSdkVersion | 24 | Android minimo. |
| compileSdkVersion | 36 | SDK compilazione. |
| targetSdkVersion | 36 | Target Android. |
| Android Gradle Plugin | 8.13.0 | Build Android. |
| GitHub Actions JDK | 21 Temurin | Build APK CI; accettato perché superiore al minimo Java 17 richiesto da toolchain moderna. |
| peaceiris/actions-gh-pages | v4 | Pubblica `docs/index.html` e APK su branch `gh-pages` dopo build su `main`. |
| androidx.work:work-runtime | 2.9.0 | Worker background alert locale. |
| Google Services Gradle Plugin | 4.4.4 | Firebase/FCM quando google-services.json è presente. |

## 3. VARIABILI D'AMBIENTE

`.env.example` è ora limitato ai soli segreti e path sensibili. Tutti i valori restano vuoti.

| Variabile | Spiegazione |
|---|---|
| API_READ_TOKEN | Token read-only per dashboard/mobile status. Admin può soddisfare read, mai il contrario. |
| VITE_API_READ_TOKEN | Copia build-time frontend/mobile del token read-only per market data e status. |
| API_ADMIN_TOKEN | Token admin per operazioni privilegiate, future config changes ed execution. |
| API_DEVICE_TOKEN | Token limitato per registrare/rimuovere token push device. |
| VITE_API_DEVICE_TOKEN | Copia build-time frontend/mobile del token device limitato. |
| API_ALERTS_TOKEN | Token limitato alla sincronizzazione della configurazione alert. |
| VITE_API_ALERTS_TOKEN | Copia build-time frontend/mobile del token alert limitato. |
| TOKEN_HASH_PEPPER | Pepper segreto per hash token/credenziali locali future. |
| DATABASE_URL | URL database solo quando contiene credenziali o punta a DB gestito sensibile. |
| CMC_API_KEY | Chiave API CoinMarketCap. |
| ANTHROPIC_API_KEY | Chiave API Anthropic/Claude. |
| TWAK_ACCESS_ID | Access ID Trust Wallet Agent Kit. |
| TWAK_HMAC_SECRET | Segreto HMAC Trust Wallet Agent Kit. |
| WALLET_ENCRYPTED_PRIVATE_KEY_PATH | Path a materiale wallet cifrato; trattato come sensibile. |
| WALLET_KEY_PASSPHRASE_ENV | Nome variabile/segreto che fornisce la passphrase wallet. |
| FCM_CREDENTIALS_PATH | Path service account Firebase; trattato come sensibile. |

Configurazioni non segrete ma specifiche dell'installazione sono in `configs/instance.example.yaml` e nel locale gitignored `configs/instance.yaml`.

Configurazioni funzionali versionate sono in `configs/risk.yaml`, `configs/strategy_spot.yaml`, `configs/strategy_perp.yaml`, `configs/eligible_tokens.yaml`.

Ordine di precedenza runtime: variabili ambiente e `.env` > `configs/instance.yaml` > YAML funzionali versionati > default Pydantic in `Settings`.

## 4. STATO STEP

| Step | Stato | Note |
|---|---|---|
| Step 0 - Setup & Architettura | Completato | Scaffold backend, env, gitignore, requirements, i18n, signal engine modulare, report e documentazione. |
| Step 1 - Backend FastAPI fondamenta | Completato | Server FastAPI avviabile, token auth read/admin, logging strutturato, health/readiness, heartbeat interno. |
| Step 2 - Migrazione Notifiche a Backend FCM | Completato | Checker backend 60s, sync alert, persistenza temporanea, FCM con app aperta/background/chiusa verificato dall'utente; boundary auth e regressione stato notifiche verificati. |
| Task intermedio - Ambiente + config refactor | Parziale | Config refactor completato e verificato; build APK riuscita in CI, deploy Pages corretto per usare branch `gh-pages` solo da `main`. |
| Task istruzioni agenti | Completato | Creato `AGENTS.md` con regole permanenti operative, sicurezza, documentazione, config, CI e step boundary. |
| Task Android package rename | Completato | Package Android/appId rinominato da `com.cryptosentinel.app` a `com.cryptosentinelai.app` per evitare conflitto con il fork/app esistente. |
| Task CI FCM Android config | Completato | Workflow aggiorna `android/app/google-services.json` da GitHub Secret base64 prima della build APK. |
| Task CI APK artifact robustness | Completato | Artifact APK caricato prima delle release GitHub; release non bloccanti per non impedire download APK/Pages. |
| Step 3 - Astrazione Dati Multi-Provider | Parziale | Adapter CMC/CoinGecko, selettore globale, checker/frontend astratti e gate completati; smoke CMC e CoinGecko reali superati. Restano i18n frontend legacy e limite Volume Profile 5m. |

## 5. DECISIONI ARCHITETTURALI

| Decisione | Motivazione |
|---|---|
| Unico loader in `backend/app/core/config.py` | Il resto del backend legge solo `Settings`; nel multi-user cambierà la sorgente dati, non i consumer. |
| `.env.example` solo segreti | Riduce rischio di versionare materiale operativo e separa ownership da strategia/config installazione. |
| `configs/instance.yaml` locale gitignored | Valori specifici dell'installazione non segreti ma non condivisibili restano fuori repo. |
| YAML funzionali versionati | Risk/strategie diventano esportabili per giudici e futuri default di sistema overridabili per utente. |
| Guardrail hard fail-closed | Portfolio floor > 1 USD, minimo 1 trade/day, drawdown cap prudenziale e 149 token eligible non sono disattivabili da config. |
| Errori Pydantic senza input | Evita che un errore di validazione stampi valori di configurazione potenzialmente sensibili. |
| FCM credentials path in `.env.example` | Anche i path a service account/segreti sono trattati come sensibili, quindi non stanno in `instance.yaml`. |
| Java locale non installato | La build Android passa da GitHub Actions, usando JDK 21 già presente nel workflow; evita SDK/JDK sulla macchina locale. |
| Deploy Pages via `gh-pages` branch | Replica il comportamento storico del progetto: ogni build su `main` aggiorna il branch `gh-pages` senza usare l'ambiente protetto `github-pages`. |
| Package Android dedicato | Il fork hackathon usa `com.cryptosentinelai.app` per non collidere con l'app CryptoSentinel esistente sul device e su Firebase/Play metadata. |
| `google-services.json` solo da secret CI | Il file Android Firebase resta gitignored e viene ricostruito in CI da `GOOGLE_SERVICES_JSON` base64 senza stampare il contenuto. |
| Artifact APK prima delle release | Il download dell'APK non deve dipendere dal successo degli step `gh release`, che sono accessori e possono fallire per collisioni/rate limit. |
| Gate segreti build APK | La CI interrompe la build prima di Vite se URL backend o token client obbligatori sono assenti, evitando APK parzialmente funzionanti. |
| FCM come unico percorso background | Rimossi WorkManager e BootReceiver: il backend controlla gli alert ogni 60 secondi e FCM consegna anche ad app chiusa. |
| Backend unica fonte notifiche | Gli hook frontend non fanno scattare notifiche, beep o popup autonomi; in foreground viene mostrato localmente solo il push FCM ricevuto. |
| Stato UI derivato dal push | Il payload FCM dei preferiti ripristina evidenziazione arancione e popup; il tap sulla notifica apre la tab Preferiti senza rieseguire controlli prezzo locali. |
| Badge preferiti persistente backend | Un push consegnato crea uno stato pending per coin. L'app lo recupera all'avvio/rientro in foreground e lo rimuove solo dopo “Ho capito”, coprendo app chiusa, avvio manuale e mancato tap sulla notifica. |
| Scope client separati | Il token device registra/rimuove solo device; il token alerts sincronizza solo alert; stato FCM richiede read e invio manuale richiede admin. |
| Stato checker autorevole lato backend | Sincronizzazioni identiche non riarmano alert già notificati e non sovrascrivono i riferimenti preferiti aggiornati mentre l'app era chiusa. |
| Adapter multi-provider, non migrazione | CMC resta il default e CoinGecko rimane selezionabile; consumer, checker e frontend dipendono solo dal contratto normalizzato. |
| Selettore globale senza fallback | Il provider è unico per tutto il processo; il cambio richiede admin e il default da Settings torna al riavvio. Fallback automatico e selezione per funzione restano V2. |
| ID applicativo stabile | L'app conserva gli ID storici usati prima dello Step 3 (`bitcoin`, `binancecoin`, ecc.); gli adapter mantengono separati slug e ID nativi dei provider. |
| Compatibilità preferiti pre-Step 3 | Gli ID CoinGecko persistiti dalle release precedenti restano l'identità dell'app; l'adapter CMC traduce alias come `binancecoin/bnb`, `ripple/xrp` e `avalanche-2/avalanche` in entrambe le direzioni. |
| Preferiti indipendenti dal mercato | L'app richiede sempre tutti gli ID preferiti e conserva gli ultimi dati validi; il selettore 50/100/200/400/600 riguarda soltanto la lista mercato. |
| Logger moduli inizializzati lazy | Provider market-data e checker notifiche acquisiscono la configurazione structlog definitiva applicata durante l'avvio backend. |
| Catalogo CMC paginato | `/v1/cryptocurrency/map` viene letto in pagine da 5.000 elementi fino a esaurimento; i preferiti meno capitalizzati non spariscono perché fuori dalla prima pagina CMC. |
| Cache prima del conteggio crediti | Una cache hit non incrementa richieste o crediti CMC; il budget osservato espone livelli ok/warning/critical/exhausted. |
| Single-flight provider | Richieste concorrenti con la stessa chiave condividono una sola chiamata esterna; le altre attendono il risultato in cache senza consumare rate limit o crediti. |
| MCP CMC separato da REST | Lo stato espone endpoint/header ufficiali senza chiavi; REST serve i flussi applicativi, MCP resta disponibile per futuri client agente. |
| OHLCV CMC segmentato | Startup include un mese di storico. Le richieste OHLCV usano `time_start`/`time_end`, finestre massime di 30 giorni e deduplicazione dei punti di confine; dati più vecchi della profondità del piano possono comunque essere rifiutati. |
| OHLCV non sintetizzato | I 5 minuti CMC sono quote storiche, non OHLCV completo; il backend non inventa volume o candele. |
| CoinGecko valido per monitoring | CoinGecko resta pienamente utilizzabile per prezzi, liste, ricerca, alert e grafici; il volume delle sue candele OHLC non è fornito e il Volume Profile 5m richiede una fonte adeguata. |
| Dashboard futura su porta 5176 | `configs/instance.example.yaml` include `dashboard.port: 5176` e CORS per localhost/127.0.0.1:5176. |
| Questioni Telegram non bloccanti | Si procede con default prudenziali del piano e si aggiornano quando arrivano risposte. |
| `AGENTS.md` come fonte regole | Centralizza le istruzioni ricorrenti per evitare di ripeterle a ogni sessione. |

## 6. NOTE PER IL REVISORE

| Area | Verifica richiesta |
|---|---|
| Security policy | Confermare che nessun `.env`, `secrets/`, service account JSON o chiave privata è stato letto o stampato. |
| Config precedence | Verificare `Settings`: env/.env > instance.yaml > YAML funzionali > default Pydantic. |
| Guardrail startup | Confermare fail-closed per `min_portfolio_value_usd <= 1`, `minimum_trades_per_day < 1`, drawdown cap oltre -15%, token count diverso da 149. |
| Multi-user readiness | Valutare se i file funzionali sono una buona base per default di sistema overridabili per utente. |
| GitHub Actions APK/Pages | Verificare che il job `build` produca `CryptoSentinel-debug.apk` e che `deploy-pages` aggiorni `gh-pages` solo su push a `main`. |
| GitHub Releases | Gli step release sono non bloccanti; se falliscono, controllare il job ma scaricare comunque l'APK dagli artifact CI. |
| Firebase Android app | Creare/scaricare un nuovo `google-services.json` per package `com.cryptosentinelai.app`, salvarlo come GitHub Secret `GOOGLE_SERVICES_JSON` in base64 e non committarlo. |
| Step 5 | Trasformare readiness DB da `not_checked` a check reale di connettività e migrare token FCM JSON su DB. |
| Step 3 CMC reale | Verificato dall'utente con chiave esportata nel processo: `1 passed, 9 deselected in 3.71s`, senza leggere `.env`. |
| Step 3 i18n | Le chiavi backend Step 3 sono EN/IT; la conversione completa dei testi legacy frontend resta da chiudere prima di dichiarare lo Step 3 completamente raggiunto. |
| Execution safety | Mantenere admin come confine netto per endpoint che muovono fondi o modificano configurazione. |
| Step boundary | Step 3 è l'ultimo step toccato; Step 4 non è stato avviato. |
| Agent onboarding | I futuri agenti devono leggere `AGENTS.md` prima di lavorare sul repository. |

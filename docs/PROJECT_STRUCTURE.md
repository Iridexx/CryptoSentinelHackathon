# PROJECT STRUCTURE

Ultimo aggiornamento: 2026-06-10

Documento di riferimento per revisione esterna. Viene aggiornato al termine di ogni step operativo.

## 1. STRUTTURA CARTELLE

```text
CryptoSentinelHackathon/ - repository CryptoSentinel + backend agente BNB Hack Track 1.
|-- AGENTS.md - regole operative permanenti per agenti AI sul repository.
|-- .github/ - automazioni CI/CD GitHub.
|   `-- workflows/build-apk.yml - workflow GitHub Actions per build APK debug con JDK 21, restore sicuro google-services da secret, artifact/release e deploy Pages su gh-pages solo da main.
|-- android/ - progetto Android Capacitor esistente.
|   |-- app/ - modulo Android principale.
|   |   |-- src/main/AndroidManifest.xml - dichiarazioni activity, receiver, provider, permessi e FCM.
|   |   |-- src/main/java/com/cryptosentinelai/app/ - codice nativo Java.
|   |   |   |-- MainActivity.java - entrypoint Android, plugin custom e worker scheduling.
|   |   |   |-- AppSettingsPlugin.java - bridge Capacitor per impostazioni, download APK e sync alert.
|   |   |   |-- PriceCheckWorker.java - WorkManager per alert/preferiti in background.
|   |   |   `-- BootReceiver.java - ripristina il worker dopo reboot dispositivo.
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
|   |   |       |-- __init__.py - aggrega router health/status/admin/notifications.
|   |   |       |-- admin.py - endpoint admin manual heartbeat.
|   |   |       |-- health.py - liveness/readiness/heartbeat con stato notifiche e DB not_checked fino Step 5.
|   |   |       |-- notifications.py - registrazione token device, status FCM e invio admin push.
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
|   |   |   |-- logging.py - setup logging strutturato structlog JSON/console.
|   |   |   `-- security/ - sicurezza API/custody.
|   |   |       |-- auth.py - autenticazione token read/device/admin fail-closed.
|   |   |       |-- headers.py - security headers e HSTS condizionale.
|   |   |       `-- wallet_custody.py - regola chiavi private solo cifrate e mai in chiaro.
|   |   |-- data/ - adapter dati mercato e cache futuri: cache, CMC, MCP.
|   |   |-- domain/ - modelli dominio separati: common, spot, perp, global_state.
|   |   |-- execution/ - adapter esecuzione futuri: spot_twak, perp_bnb_sdk, wallet, x402.
|   |   |-- i18n/locales/ - traduzioni backend en.json e it.json.
|   |   |-- notifications/ - sistema notifiche server-side.
|   |   |   |-- service.py - orchestration registry + FCM client.
|   |   |   `-- fcm/ - integrazione Firebase Cloud Messaging.
|   |   |       |-- client.py - wrapper Firebase Admin SDK, delivery e skipped se non configurato.
|   |   |       `-- token_store.py - registro token FCM persistente su JSON fino allo Step 5.
|   |   |-- observability/ - namespace metriche, health, replay/export futuri.
|   |   |-- persistence/ - migrazioni, modelli DB e repository futuri.
|   |   |-- schemas/notifications.py - schema device token, notification request/response e status.
|   |   |-- services/ - namespace application services.
|   |   `-- tasks/ - namespace scheduled/background tasks.
|   |-- scripts/.gitkeep - placeholder script operativi backend.
|   `-- tests/ - test backend placeholder.
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
|       `-- report_config_refactor.md - report task intermedio ambiente/config.
|-- plans/ - piani operativi.
|   `-- Plan_forHackathon.md - piano completo BNB Hack Track 1.
|-- public/ - asset statici frontend/PWA.
|-- scripts/ - script frontend/tooling.
|   `-- gen-icons.mjs - generazione icone.
|-- src/ - frontend React/TypeScript esistente.
|   |-- components/ - componenti UI CryptoSentinel.
|   |-- hooks/ - hook dati, alert, preferiti, valuta, search e refresh.
|   |-- utils/ - notifiche, update, haptics, audio, energy saving.
|   |   `-- notifications.ts - notifiche locali + registrazione token FCM verso backend via env Vite.
|   |-- App.tsx - root app mobile/web.
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
| httpx | 0.28.1 | Client HTTP async per integrazioni esterne future. |
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
| API_ADMIN_TOKEN | Token admin per operazioni privilegiate, future config changes ed execution. |
| API_DEVICE_TOKEN | Token limitato per registrare/rimuovere token push device. |
| VITE_API_DEVICE_TOKEN | Copia build-time frontend/mobile del token device limitato. |
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
| Step 2 - Migrazione Notifiche a Backend FCM | Parziale | Backend FCM, token registry, severity model, endpoint e mobile token registration implementati; delivery reale richiede credenziali Firebase e build Android. |
| Task intermedio - Ambiente + config refactor | Parziale | Config refactor completato e verificato; build APK riuscita in CI, deploy Pages corretto per usare branch `gh-pages` solo da `main`. |
| Task istruzioni agenti | Completato | Creato `AGENTS.md` con regole permanenti operative, sicurezza, documentazione, config, CI e step boundary. |
| Task Android package rename | Completato | Package Android/appId rinominato da `com.cryptosentinel.app` a `com.cryptosentinelai.app` per evitare conflitto con il fork/app esistente. |
| Task CI FCM Android config | Completato | Workflow aggiorna `android/app/google-services.json` da GitHub Secret base64 prima della build APK. |
| Step 3 - Migrazione CoinGecko a CMC | Non iniziato | Da avviare solo dopo approvazione. |

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
| Firebase Android app | Creare/scaricare un nuovo `google-services.json` per package `com.cryptosentinelai.app`, salvarlo come GitHub Secret `GOOGLE_SERVICES_JSON` in base64 e non committarlo. |
| Step 5 | Trasformare readiness DB da `not_checked` a check reale di connettività e migrare token FCM JSON su DB. |
| Execution safety | Mantenere admin come confine netto per endpoint che muovono fondi o modificano configurazione. |
| Step boundary | Step 3 non iniziato: nessuna migrazione CoinGecko -> CMC implementata. |
| Agent onboarding | I futuri agenti devono leggere `AGENTS.md` prima di lavorare sul repository. |

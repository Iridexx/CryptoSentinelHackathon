# CryptoSentinel Backend

FastAPI backend for the BNB Hack Track 1 autonomous trading agent.

The backend includes the Step 3 provider-neutral market data layer on top of the Step 2 notification path: CoinMarketCap and CoinGecko adapters, one global manual selector, normalized responses, CMC rate limiting and credit-aware caching, CMC MCP metadata, and a notification checker that uses the selected provider. Trading, database persistence, and agent decisions are implemented in later steps.

## Current Scope

- FastAPI application factory in `backend/app/main.py`.
- Public liveness endpoint for process supervision.
- Authenticated readiness, heartbeat, and status endpoints.
- Admin-only manual heartbeat endpoint.
- Structured JSON/console logging via `structlog`.
- CORS and reverse-proxy header support for future HTTPS deployment.
- Provider-neutral market list, price, search, and OHLCV endpoints.
- CMC primary adapter and CoinGecko secondary adapter with no automatic fallback.
- Admin-only global provider selection, reset to the configured default on restart.
- Conservative security headers, with HSTS enabled when `API_BASE_URL` uses `https://`.
- In-memory heartbeat loop used by health checks.
- Server-side notification service with `critical`, `warning`, and `info` severities.
- FCM token registry persisted to local JSON until database persistence is introduced.
- Alert configuration and checker state persisted to local JSON until database persistence is introduced.
- Background price checker for price thresholds, ranges, and favorite-coin percentage moves.
- Firebase Admin SDK delivery client that returns `skipped` when FCM is not configured instead of pretending success.
- Single `Settings` loader that merges `.env` secrets with `configs/*.yaml`.
- Startup guardrails for competition qualification: portfolio floor, daily trade minimum, drawdown cap, and 149 eligible tokens.

## Run Locally

Use the startup scripts in `backend/scripts/`. They activate the virtualenv automatically, read host and port from `Settings` (no hardcoded values), and accept an optional flag to enable Uvicorn's reload mode for local development.

**First-time setup** — create the virtualenv and install dependencies:

```bash
python -m venv backend/.venv
# Windows
backend/.venv/Scripts/activate
# Linux / macOS
source backend/.venv/bin/activate

pip install -r backend/requirements.txt
```

**Windows (PowerShell) — run from the project root:**

```powershell
# Production (no reload)
.\backend\scripts\run_backend.ps1

# Development (--reload attivo)
.\backend\scripts\run_backend.ps1 -Dev
```

**Linux / macOS — run from the project root:**

```bash
chmod +x backend/scripts/run_backend.sh

# Production
./backend/scripts/run_backend.sh

# Development
./backend/scripts/run_backend.sh --dev
```

Host and port are read from `configs/instance.yaml` via `Settings`; do not duplicate those values in the scripts or environment. The `-Dev` / `--dev` flag enables `--reload` only when explicitly passed.

Create local config files first. The repository only includes `.env.example` and `configs/instance.example.yaml`; never commit `.env`, `configs/instance.yaml`, or real secrets.

Minimum local `.env` secrets for authenticated endpoints:

```env
API_READ_TOKEN=replace-with-local-read-token
API_ADMIN_TOKEN=replace-with-local-admin-token
API_DEVICE_TOKEN=replace-with-limited-device-registration-token
API_ALERTS_TOKEN=replace-with-limited-alert-sync-token
CMC_API_KEY=replace-with-cmc-key
```

Minimum `configs/instance.yaml` installation values for real FCM delivery:

```yaml
fcm:
  enabled: true
  project_id: your-firebase-project-id
  critical_topic: cryptosentinel-critical
  token_store_path: backend/storage/fcm_tokens.json
```

Minimum `.env` secret for real FCM delivery:

```env
FCM_CREDENTIALS_PATH=C:/secure/path/firebase-service-account.json
```

The Firebase service account JSON must not be committed.

## Configuration Precedence

Runtime precedence is:

1. Environment variables and `.env`.
2. Local `configs/instance.yaml`.
3. Versioned functional YAML defaults in `configs/`.
4. Pydantic defaults inside `Settings`.

Application code must read configuration only through `backend.app.core.config.Settings`.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health/live` | Public | Process liveness. |
| GET | `/health/ready` | Read/Admin token | Readiness and dependency status. |
| GET | `/health/heartbeat` | Read/Admin token | Internal heartbeat state. |
| GET | `/api/v1/status` | Read/Admin token | Backend mode, user scope, and conservative risk defaults. |
| POST | `/api/v1/admin/heartbeat` | Admin token | Manual admin heartbeat tick. |
| GET | `/api/v1/notifications/status` | Read/Admin token | FCM subsystem status and token count. |
| POST | `/api/v1/notifications/devices` | Device/Admin token | Register an FCM device token. |
| POST | `/api/v1/notifications/devices/unregister` | Device/Admin token | Remove an FCM device token. |
| POST | `/api/v1/notifications/send` | Admin token | Send an FCM notification to registered devices. |
| POST | `/api/v1/alerts/sync` | Alerts/Admin token | Replace the mobile alert configuration used by the backend checker. |
| GET | `/api/v1/alerts/pending-favorites` | Alerts/Admin token | Return favorite-move badges awaiting user acknowledgement. |
| DELETE | `/api/v1/alerts/pending-favorites/{coin_id}` | Alerts/Admin token | Acknowledge and remove one favorite-move badge. |
| GET | `/api/v1/market-data/provider` | Read/Admin token | Active provider, rate/cache/credit diagnostics, and CMC MCP status. |
| PUT | `/api/v1/market-data/provider` | Admin token | Select CMC or CoinGecko globally until backend restart. |
| GET | `/api/v1/market-data/markets` | Read/Admin token | Normalized market-cap list from the selected provider. |
| GET | `/api/v1/market-data/prices` | Read/Admin token | Normalized current prices for assets and currencies. |
| GET | `/api/v1/market-data/search` | Read/Admin token | Search through the selected provider. |
| GET | `/api/v1/market-data/ohlcv` | Read/Admin token | Normalized OHLCV history where supported. |

The default provider is configured under `market_data.provider`. Developer settings may change it at runtime with an admin token held only in component state. No automatic fallback is implemented.

CMC Startup includes one month of historical data. OHLCV requests always send explicit `time_start` and `time_end` values and are split into windows of at most 30 days; boundary points are deduplicated after normalization. Requests older than the plan's one-month historical depth may still be rejected by CMC even when correctly segmented. The documented 5-minute historical capability is quotes-only, so unsupported 5-minute OHLCV is rejected instead of being synthesized.

Authentication accepts either:

```http
Authorization: Bearer <token>
```

or:

```http
X-API-Token: <token>
```

## Mobile Push Registration

The mobile app uses `@capacitor/push-notifications` to obtain the FCM registration token and posts it to `/api/v1/notifications/devices` when these Vite variables are configured at build time:

```env
VITE_BACKEND_API_BASE_URL=https://your-backend.example
VITE_API_READ_TOKEN=replace-with-limited-read-token
VITE_API_DEVICE_TOKEN=replace-with-limited-device-registration-token
VITE_API_ALERTS_TOKEN=replace-with-limited-alert-sync-token
```

If those variables are missing, foreground local notifications continue to work while remote push registration and closed-app delivery are skipped.

## Directory Structure

```text
backend/
|-- app/
|   |-- api/ - FastAPI routers and API dependencies.
|   |-- agent/ - autonomous agent heartbeat, brain, loops, risk engine, and modular signals.
|   |-- core/ - configuration, logging, auth, security headers, and runtime primitives.
|   |-- data/ - market data adapters, CMC integration, MCP integration, and cache boundaries.
|   |-- domain/ - domain models split by common, spot, perp, and global state.
|   |-- execution/ - trading execution adapters for TWAK, BNB SDK/EIP-712, x402, and wallet custody.
|   |-- i18n/ - translation files and localization helpers.
|   |-- notifications/ - alert state, background price checker, notification service, and FCM integration.
|   |-- observability/ - logging, metrics, health, and replay/export support.
|   |-- persistence/ - database models, repositories, and migrations.
|   |-- schemas/ - API schemas and DTOs.
|   |-- services/ - application services coordinating domain logic.
|   `-- tasks/ - scheduled jobs and background task entrypoints.
|-- scripts/ - startup and operational scripts (run_backend.ps1, run_backend.sh).
|-- tests/ - unit and integration tests.
`-- requirements.txt - backend Python dependencies.
```

## Security Notes

- `API_READ_TOKEN` can read health/status endpoints.
- `API_DEVICE_TOKEN` can only register/unregister push tokens.
- `API_ALERTS_TOKEN` can only replace the current alert configuration.
- `API_ADMIN_TOKEN` can call admin endpoints and send notifications.
- Device token registration deliberately does not use read or admin tokens in the mobile app.
- If tokens are missing, protected endpoints return `503` instead of silently running unauthenticated.
- Wallet private keys must remain encrypted at rest. Store only encrypted key paths and passphrase source names in environment variables.
- HTTPS is expected at the reverse proxy on VPS. The app is prepared for proxy headers and HSTS once `API_BASE_URL=https://...` is configured.

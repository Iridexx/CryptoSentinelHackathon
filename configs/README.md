# Configuration Model

CryptoSentinel uses one runtime loading point: `backend/app/core/config.py`.
Application code must depend on `Settings` only and must not read YAML files,
`.env`, or secret files directly.

## Categories

1. Secrets: local `.env`, never versioned. The tracked `.env.example` contains
   only empty secret keys and sensitive secret-file paths.
2. Installation config: `configs/instance.yaml`, never versioned. The tracked
   `configs/instance.example.yaml` is the template for host-specific,
   non-secret values such as API URL, CORS origins, BSC network, wallet address,
   FCM project id, and execution mode.
3. Functional config: versioned YAML files in `configs/`. These contain default
   risk and strategy parameters that can later become per-user overrides.

## Precedence

Runtime precedence is explicit:

1. Environment variables and `.env`.
2. `configs/instance.yaml`.
3. Versioned functional defaults:
   `configs/risk.yaml`, `configs/strategy_spot.yaml`,
   `configs/strategy_perp.yaml`, and `configs/eligible_tokens.yaml`.
4. Pydantic field defaults inside `Settings`.

## Hard Guardrails

The following qualification guardrails are validated at startup and cannot be
disabled by config:

- Minimum portfolio value must stay above 1 USD.
- Minimum trade frequency must be at least 1 trade per day.
- Drawdown cap must be negative and no looser than -15%.
- Eligible-token universe must contain exactly 149 competition entries.

If any source violates these rules, `Settings` raises a validation error and the
backend refuses to start.

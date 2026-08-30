# Report — R1: config della scheda "Bank" / Riserva di Valore

Data: 2026-08-30
Contesto: `plans/Plan_Reserve.md`, step R1.

## COSA È STATO FATTO

Introdotta la configurazione della riserva, senza ancora toccare viste, risk
manager o loop dell'agente:

1. `configs/reserve.yaml` — nuovo file funzionale versionato: 5 hard asset
   (BTC/ETH/BNB/SOL/TRX) con pesi target 40/30/20/5/5, banda di drift, parametri
   sweep profitti, cooldown prelievi, toggle, indirizzi PancakeSwap e simboli
   spot Aster per l'esecuzione live futura.
2. `backend/app/core/config.py`:
   - `reserve.yaml` aggiunto a `FUNCTIONAL_CONFIG_FILES`;
   - sezione `reserve` gestita in `_flatten_config` come sotto-config strutturata
     (come `eligible_tokens`);
   - nuovi modelli tipizzati `ReserveAssetConfig` e `ReserveConfig` con
     `model_validator` di coerenza interna;
   - nuovo campo `Settings.reserve: ReserveConfig`.
3. `backend/app/schemas/reserve.py` — `ReserveSettings` (sottoinsieme tunabile:
   pesi target, drift, sweep, cooldown, toggle), `ReserveTargetWeight`,
   `ReserveSettingsResponse` con `source`; `from_config()` e
   `reconcile_with_config()` per mantenere valido un override dopo un cambio
   della lista asset nel YAML.
4. `backend/app/domain/reserve/` — nuovo package. `settings.py`:
   `load_reserve_settings` / `save_reserve_settings`, override persistito in
   `runtime_state` (chiave `reserve_settings`), degrada al default di config se
   la persistenza non è disponibile o il payload è stale. Stesso pattern di
   `mobile_agent_settings`.

## COME È STATO FATTO

- La lista asset + indirizzi + simboli spot resta **solo** in `reserve.yaml`
  (non user-editable). Solo pesi/drift/sweep/cooldown/toggle sono nel modello
  runtime `ReserveSettings`.
- Validazioni non-hard (non toccano i guardrail di qualificazione): somma pesi
  = 100 ± 0.01, simboli unici, `sweep_pct` in [0,100], `sweep_interval_hours`
  ≥ 1, `drift_band_pct` > 0, soglie USD ≥ 0. Con `enabled: false` i controlli
  su pesi/asset sono saltati.
- I guardrail hard esistenti (148 eligible token, floor portfolio, drawdown
  cap, ecc.) sono invariati.

## COSA È STATO VERIFICATO

Interprete: `backend\.venv\Scripts\python.exe`.

- `pytest backend/tests/unit/test_reserve_config.py` — 12 test nuovi, tutti
  verdi (caricamento YAML, validazioni ReserveConfig, `from_config`,
  `reconcile_with_config`, round-trip load/save override con `runtime_state`
  monkeypatchato).
- `pytest -k "config or reserve or persistence or venue"` — 81 passati, nessuna
  regressione.
- Costruzione `Settings(**load_yaml_settings())` OK: `reserve.enabled=True`,
  asset `[BTC, ETH, BNB, SOL, TRX]`, somma pesi 100.0.
- `import backend.app.main` OK (startup path invariato).
- `ruff check` pulito su tutti i file nuovi/modificati.

## SCOSTAMENTI DAL PIANO

Nessuno. R1 come da piano; l'esito di R1b (venue live = PancakeSwap, TRX senza
spot Aster) è già riflesso in `reserve.yaml` (`aster_spot_symbol: null` per TRX).

## QUESTIONI APERTE

- Indirizzi BEP20 in `reserve.yaml` da verificare on-chain prima di qualunque
  uso live (marcati con commento "verify"). Non usati nella fase simulata.
- R2: modelli ORM `ReserveHolding` / `ReserveTransaction` / `ReserveSnapshot` +
  repository + upgrade colonne SQLite.

## STATO DELIVERABLE

- `configs/reserve.yaml` — creato.
- `backend/app/core/config.py` — `ReserveConfig`/`ReserveAssetConfig` +
  `Settings.reserve`.
- `backend/app/schemas/reserve.py` — creato.
- `backend/app/domain/reserve/{__init__,settings}.py` — creati.
- `backend/tests/unit/test_reserve_config.py` — creato (12 test).
- Doc: `PROJECT_STRUCTURE.md`, `configs/README.md`, `AGENTS.md` aggiornati.
- Prossimo step: **R2** su approvazione.

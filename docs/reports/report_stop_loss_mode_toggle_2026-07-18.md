# Toggle stop loss ATR/Min-Max 14 - 2026-07-18

## 1. COSA È STATO FATTO

- Verificato il toggle esistente per la modalita' stop loss Spot e Perp.
- Corretto il percorso runtime: i valori `spot_sl_mode` e `perp_sl_mode` salvati dall'app vengono ora applicati al `Settings` live.
- Allineato il fallback dell'AgentService ai valori reali di `Settings`.
- Aggiunti test per dimostrare che i signal engine usano davvero minimo/massimo delle ultime 14 candele quando il toggle e' su `lowest`.

## 2. COME È STATO FATTO

- Estesa la mappatura `_MOBILE_TO_SETTINGS` in `backend/app/api/routes/mobile_agent.py`.
- `_settings_from_config()` ora restituisce `settings.spot_sl_mode` e `settings.perp_sl_mode` invece di forzare `atr`.
- `AgentService._ms` ora include i valori `spot_sl_mode` e `perp_sl_mode` nel fallback da config.
- I signal engine usano `atr` come fallback se un vecchio stub/config non espone ancora i campi `*_sl_mode`.
- Aggiunto `backend/tests/unit/test_signal_stop_loss_modes.py`.
- Aggiornati i documenti `docs/Uscite_Spot.md` e `docs/Uscite_Perpetual.md`.

## 3. COSA È STATO VERIFICATO

- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_mobile_agent_step7.py backend/tests/unit/test_signal_stop_loss_modes.py -q`
- Esito: `6 passed in 9.19s`.
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_mobile_agent_step7.py backend/tests/unit/test_signal_stop_loss_modes.py backend/tests/unit/test_agent_step6.py -q`
- Esito: `67 passed in 51.01s`.

## 4. SCOSTAMENTI DAL PIANO

- Nessuno scostamento: il toggle era gia' previsto dalla UI, ma mancava il collegamento runtime completo verso il Settings usato dai segnali.

## 5. QUESTIONI APERTE

- Verificare su APK/dispositivo reale il salvataggio del toggle dal setup agente contro backend avviato.

## 6. STATO DELIVERABLE

- Deliverable completato: il toggle ATR/Min-Max 14 e' operativo per Spot e Perp nel backend e coperto da test.

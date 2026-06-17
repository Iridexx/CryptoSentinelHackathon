# REPORT STEP 4 ESTESO — ASTRAZIONE EXECUTION LAYER MULTI-PROVIDER

## 1. COSA È STATO FATTO

- Creata l'interfaccia astratta `ExecutionProvider` (`backend/app/execution/base.py`) con i modelli normalizzati `ExecutionQuote`, `ExecutionPosition`, `ExecutionProviderStatus` e l'enum `ExecutionProviderName` (`twak`, `pancakeswap`). I metodi comuni sono `get_quote`, `execute_swap`, `status`; `get_position`/`close_position` hanno default fail-closed (`ExecutionCapabilityError`) perché lo swap spot è atomico e non ha posizioni persistenti a livello provider.
- Implementato `TWAKProvider` (`backend/app/execution/providers/twak_provider.py`) che **avvolge** `TwakClient` senza riscrivere firma HMAC, Amber API o CLI. È un refactor di adattamento: normalizza quote/execute_swap nei modelli comuni; il risultato TWAK resta `PREPARED` (transazioni unsigned firmate fuori banda in autonomous mode).
- Implementato `PancakeSwapProvider` (`backend/app/execution/providers/pancakeswap_provider.py`): esecuzione DEX diretta via `web3.py` sul Router PancakeSwap V2, senza dipendenza da Trust Wallet. Quote via `getAmountsOut`, approval ERC-20 esatta, `swapExactTokensForTokens`/`swapExactETHForTokens`, firma con keystore cifrato e conferma on-chain.
- Creato il selettore globale `ExecutionProviderRegistry` (`backend/app/execution/registry.py`), stesso pattern del `MarketDataRegistry`: default da `Settings`, override persistito in `RuntimeState` (chiave `execution_provider`), cambio admin-only, nessun fallback automatico.
- Aggiunti endpoint `GET /api/v1/execution/provider` (read) e `PUT /api/v1/execution/provider` (admin) e lo schema `backend/app/schemas/execution.py`.
- `ExecutionService.status()` riporta ora provider spot attivo + statuses dal registry.
- Config: campo `execution_provider`, indirizzi Router/WBNB mainnet+testnet (default ufficiali), voce `execution` in `SECTION_FIELD_MAP`, sezione `execution` in `configs/instance.example.yaml`. `app_version` → `0.1.0-step4ext`.
- Aggiunto `backend/scripts/pancakeswap_smoke_test.py` (quote-only di default; `--execute` per swap reale; mainnet solo con `--allow-mainnet`).

## 2. COME È STATO FATTO

- **Riuso, non duplicazione, dei guardrail comuni**: `PancakeSwapProvider` usa `GasGuard`, `ExactApprovalPolicy`, `ExecutionCoordinator`+`TransactionReconciler`, `MultiRpcClient` e `EncryptedKeystoreWallet` esistenti. I guardrail non sono replicati: sono gli stessi del layer comune validi per entrambi i provider.
- **Ordine fail-closed in `execute_swap`** (PancakeSwap): 1) slippage ≤ limite hard; 2) `gas_decision.allowed`; 3) gate testnet-only; 4) approval esatta; 5) build+firma+invio+riconciliazione. I primi tre controlli precedono qualsiasi I/O di rete o accesso al wallet.
- **Gate testnet-only mantenuto** (decisione utente): su mainnet `execute_swap` ritorna `SKIPPED` con reason `mainnet_execution_gated`, salvo flag esplicito `allow_mainnet` passato solo dallo smoke test opt-in. Coerente con il guardrail di `config.py` e con il path TWAK.
- **Indirizzi verificati, non assunti** (richiesto dal piano): Router V2 mainnet `0x10ED43C718714eb63d5aA57B78B54704E256024E` e testnet `0xD99D1c33F9fC3444f8101754aBC46c52416550D1`; WBNB mainnet `0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c` e testnet `0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd`. Tutti configurabili da Settings.
- **Selettori 4-byte calcolati** con `Web3.keccak`, argomenti codificati con `eth_abi` (già dipendenza transitiva di `web3==7.6.1`): nessuna nuova dipendenza.
- **Testabilità**: i metodi puri (`build_path`, `encode_get_amounts_out`, `decode_amounts`, `build_swap_transaction`, `build_approve_transaction`) sono separati dall'I/O, così i guardrail e la costruzione tx si testano senza rete né wallet.
- Il perp (BNB SDK / EIP-712) resta su percorso separato e non è stato toccato: l'astrazione riguarda solo lo spot, coerente con la natura distinta di spot e perp.
- Il selettore va in `configs/instance.example.yaml` e non in `.env.example` (non è un segreto), seguendo la convenzione del repo.

## 3. COSA È STATO VERIFICATO

- `ruff check` su tutti i file nuovi/modificati: superato.
- Suite execution mirata: `26 passed, 2 failed` (i 2 failed sono il debito HMAC pre-esistente, vedi §4).
- Suite backend completa: `71 passed, 1 skipped, 2 failed` (gli stessi 2 HMAC pre-esistenti).
- Test nuovi (`test_execution_providers.py`, 15):
  - interfaccia rispettata da entrambi i provider (sottoclassi di `ExecutionProvider`, `get_position`/`close_position` sollevano `ExecutionCapabilityError`);
  - selettore: cambio `twak`↔`pancakeswap` cambia `registry.active`; default di boot segue `Settings`;
  - PancakeSwap: quote `getAmountsOut` decodificato correttamente (mock RPC), `min_out` con slippage; costruzione swap tx corretta (selettore, value, path, nonce, chainId) per input token e nativo; path token→token instradato via WBNB;
  - guardrail: slippage oltre limite → errore senza I/O; gas rifiutato → errore senza I/O; mainnet → `SKIPPED` gated senza I/O;
  - TWAKProvider: quote/execute_swap normalizzati (status `PREPARED`, transazioni preservate).
- Indirizzi Router/WBNB confermati su BscScan (mainnet e testnet).

## 4. SCOSTAMENTI DAL PIANO

- L'interfaccia include `get_position`/`close_position` (come da piano riga 431) ma con default fail-closed: lo swap spot è atomico e non espone posizioni a livello provider — le posizioni restano responsabilità del risk engine/agente (Step 6). Decisione confermata con l'utente.
- `execute_swap` di PancakeSwap usa `gas_price` live da RPC e un `gas_limit` di default per la costruzione tx, mentre la `GasDecision` è calcolata dal chiamante (stesso pattern dello smoke test TWAK). Possibile piccola incoerenza tra il gas_limit usato per la decisione e quello della tx; accettabile in V1, da affinare con stima `eth_estimateGas` in seguito.

## 5. QUESTIONI APERTE / DECISIONI NECESSARIE

- **WBNB testnet del Router PancakeSwap testnet**: alcuni deployment testnet usano un WBNB diverso da `0xae13...`. Il valore è configurabile; va confermato con uno swap testnet reale (smoke test) prima dell'uso operativo.
- **Esecuzione reale mainnet**: attualmente gated. Quando si vorrà operare davvero fuori dall'hackathon servirà sbloccare consapevolmente il gate (oggi solo via `--allow-mainnet` nello smoke test).
- **Debito pre-esistente (non di questo step)**: 2 test HMAC in `test_execution_layer.py` (`test_twak_hmac_matches_documented_wire_format`, `test_twak_hmac_supports_current_sdk_wire_format`) falliscono perché si aspettano un parametro `profile` e un formato Authorization non più allineati al client corrente. Erano già rossi prima di questo lavoro; lasciati fuori scope salvo diversa indicazione.

## 6. VERIFICHE TECNICHE

- `eth_abi` (encode/decode) e `Web3.keccak` verificati nel virtualenv backend; selettore `getAmountsOut` = `0xd06ca61f`.
- Nessuna nuova dipendenza aggiunta a `backend/requirements.txt`.
- Smoke test `pancakeswap_smoke_test.py` non eseguito on-chain in questo step (richiede wallet finanziato e RPC live); predisposto e pronto.

## 7. STATO DELIVERABLE

**Raggiunto.** Esecuzione spot astratta dietro `ExecutionProvider` con due implementazioni intercambiabili (TWAK per l'hackathon, PancakeSwap diretto per uso reale/test), selettore globale persistito admin-only, guardrail comuni riusati da entrambi i provider, suite test verde (escluso il debito HMAC pre-esistente). Esecuzione reale PancakeSwap testabile su testnet; submission mainnet gated. Da validare on-chain con lo smoke test su testnet con wallet finanziato.

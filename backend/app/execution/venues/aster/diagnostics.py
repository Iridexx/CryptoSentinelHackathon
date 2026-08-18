"""Aster connection diagnostics — the single source used by App, Dashboard and CLI.

STRICTLY READ-ONLY. Every call made here is a GET on an informational endpoint:
this code cannot place, modify or cancel an order, and cannot move funds.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.app.core.logging import get_logger
from backend.app.execution.venues.aster.client import AsterClient, AsterError, short_address

logger = get_logger("execution.venue.aster.diagnostics")

OK = "ok"
WARNING = "warning"
ERROR = "error"
CRITICAL = "critical"


@dataclass
class Check:
    """One diagnostic step, in user-facing language."""

    key: str
    label: str
    status: str
    detail: str
    technical: str | None = None


@dataclass
class DiagnosticsReport:
    overall: str
    summary: str
    checks: list[Check] = field(default_factory=list)
    started_at: str = ""
    duration_ms: int = 0
    account: str | None = None
    subaccount_name: str | None = None
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checks"] = [asdict(c) for c in self.checks]
        return data


#: Aster answers -1000 on every account/history endpoint of an account that has
#: never been funded (balance, positionRisk, income, commissionRate, userTrades),
#: while configuration endpoints keep answering normally. The message it attaches
#: says "Signature check failed", which is misleading: the same credentials are
#: accepted on /fapi/v3/agent moments earlier.
_UNFUNDED_ACCOUNT_CODE = "-1000"


def _looks_unfunded(exc: AsterError) -> bool:
    """True when the failure is the one an account without deposits produces."""
    return (exc.code or "") == _UNFUNDED_ACCOUNT_CODE


_UNFUNDED_DETAIL = (
    "Il conto Aster non ha ancora ricevuto depositi: finché non viene alimentato "
    "Aster non espone questi dati. Le credenziali sono valide (verificate al passo "
    "precedente). Esegui di nuovo il test dopo il primo deposito."
)


def _describe(exc: AsterError) -> tuple[str, str]:
    """Translate an Aster failure into something a person can act on."""
    code = (exc.code or "").upper()
    status = exc.status
    if code == "TIMEOUT":
        return ("Aster non ha risposto entro il tempo previsto. "
                "Riprova; se persiste, verifica la connessione della VPS.", code)
    if code == "NETWORK":
        return ("Impossibile raggiungere Aster. Verifica connettività di rete e "
                "che l'indirizzo del servizio sia corretto.", code)
    if status in (401, 403):
        return ("Aster ha rifiutato l'autenticazione. Verifica indirizzo del wallet API, "
                "chiave di firma e che la chiave non sia scaduta.", code or str(status))
    if status == 429:
        return ("Troppe richieste in poco tempo (rate limit di Aster). "
                "Attendi qualche secondo e riprova.", code or "429")
    if status and 500 <= status < 600:
        return ("Aster ha restituito un errore interno. Il problema è dalla loro parte: "
                "riprova più tardi.", code or str(status))
    return (f"Aster ha rifiutato la richiesta: {exc}", code or (str(status) if status else "-"))


async def run_connection_test(settings) -> DiagnosticsReport:
    """Run the full read-only diagnostic sequence."""
    started = time.perf_counter()
    started_at = datetime.now(UTC)
    checks: list[Check] = []
    logger.info("aster_test_started")

    base_url = getattr(settings, "aster_base_url", "")
    account_address = getattr(settings, "aster_account_address", "")
    api_wallet = getattr(settings, "aster_api_wallet_address", "")
    private_key = getattr(settings, "aster_api_wallet_private_key", "")
    subaccount = getattr(settings, "aster_subaccount_name", "")

    def finish(overall: str, summary: str, *, blocked: bool = False) -> DiagnosticsReport:
        duration = int((time.perf_counter() - started) * 1000)
        logger.info("aster_test_completed", overall=overall, duration_ms=duration)
        return DiagnosticsReport(
            overall=overall,
            summary=summary,
            checks=checks,
            started_at=started_at.isoformat(),
            duration_ms=duration,
            account=short_address(account_address),
            subaccount_name=subaccount or None,
            blocked=blocked,
        )

    # 0. Enabled check
    enabled = getattr(settings, "aster_enabled", False)
    if not enabled:
        checks.append(Check(
            "enabled", "Abilitazione", CRITICAL,
            "Aster è disabilitato (ASTER_ENABLED=false nel .env). "
            "Imposta ASTER_ENABLED=true e riavvia il server per attivare il venue perp.",
        ))
        return finish(CRITICAL, "Aster disabilitato — imposta ASTER_ENABLED=true nel .env.")

    # 1. Configuration
    missing = [
        name
        for name, value in (
            ("indirizzo account", account_address),
            ("indirizzo wallet API", api_wallet),
            ("chiave di firma", private_key),
        )
        if not value
    ]
    if missing:
        checks.append(Check(
            "config", "Configurazione", ERROR,
            "Mancano queste voci nella configurazione: " + ", ".join(missing)
            + ". Vanno inserite nel file .env sulla VPS.",
        ))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")
    checks.append(Check(
        "config", "Configurazione", OK,
        f"Configurazione presente. Account {short_address(account_address)}, "
        f"wallet API {short_address(api_wallet)}.",
    ))

    client = AsterClient(
        base_url=base_url,
        account_address=account_address,
        api_wallet_address=api_wallet,
        api_wallet_private_key=private_key,
    )

    # 2. Key/address coherence
    if not client.signer_matches_key():
        checks.append(Check(
            "signer", "Coerenza credenziali", ERROR,
            "La chiave di firma non corrisponde all'indirizzo del wallet API configurato. "
            "Probabilmente appartengono a due wallet diversi.",
        ))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")
    checks.append(Check(
        "signer", "Coerenza credenziali", OK,
        "La chiave di firma corrisponde all'indirizzo del wallet API.",
    ))

    # 3. Reachability (public, unsigned)
    try:
        info = await client.public_exchange_info()
        markets = len(info.get("symbols", [])) if isinstance(info, dict) else 0
        checks.append(Check(
            "reachability", "Connessione API", OK,
            f"Servizio Aster raggiungibile: {markets} mercati pubblicati.",
        ))
    except AsterError as exc:
        if exc.status in (401, 403, 404):
            detail = (
                f"Il servizio Aster ha rifiutato la richiesta pubblica (codice {exc.status}). "
                "Questa chiamata non usa credenziali: verifica l'indirizzo del servizio "
                "configurato in ASTER_BASE_URL, oppure un blocco di rete verso quell'host."
            )
            code = str(exc.status)
        else:
            detail, code = _describe(exc)
        checks.append(Check("reachability", "Connessione API", ERROR, detail, code))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")

    # 4. Authentication — the only read endpoint that really verifies the signature.
    #
    # Aster answers 200 on /fapi/v3/accountWithJoinMargin even for a forged
    # signature, so it cannot tell a valid credential from an invalid one.
    # /fapi/v3/agent does: it rejects a signature altered by a single byte, and
    # it also reports whether this API wallet is still registered and what it
    # is allowed to do.
    agents: Any = None
    try:
        agents = await client.agents()
        checks.append(Check(
            "auth", "Autenticazione", OK,
            "Aster ha accettato la firma: le credenziali sono valide.",
        ))
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("auth", "Autenticazione", ERROR, detail, code))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")

    # 5. The API wallet must be registered, unexpired and allowed to read.
    entry = None
    for item in agents if isinstance(agents, list) else []:
        if str(item.get("agentAddress", "")).lower() == api_wallet.lower():
            entry = item
            break

    if entry is None:
        checks.append(Check(
            "permissions", "Permessi wallet API", CRITICAL,
            f"Il wallet API {short_address(api_wallet)} non risulta registrato su questo account "
            "Aster. Va autorizzato dalla pagina API di Aster, oppure l'indirizzo configurato "
            "appartiene a un altro account.",
        ))
        return finish(CRITICAL, "CONNESSIONE ASTER: ERRORE CRITICO", blocked=True)

    expired_ms = entry.get("expired")
    if isinstance(expired_ms, int | float) and expired_ms > 0:
        expiry = datetime.fromtimestamp(expired_ms / 1000, UTC)
        if expiry <= datetime.now(UTC):
            checks.append(Check(
                "permissions", "Permessi wallet API", CRITICAL,
                f"Il wallet API è scaduto il {expiry:%d/%m/%Y}. Va rigenerato dalla pagina API di Aster.",
            ))
            return finish(CRITICAL, "CONNESSIONE ASTER: ERRORE CRITICO", blocked=True)
        expiry_note = f" Scadenza: {expiry:%d/%m/%Y}."
    else:
        expiry_note = ""

    if not entry.get("canRead", False):
        checks.append(Check(
            "permissions", "Permessi wallet API", ERROR,
            "Il wallet API non ha il permesso di lettura: i dati dell'account restano inaccessibili.",
        ))
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")

    granted = [
        label
        for label, flag in (("lettura", "canRead"), ("spot", "canSpotTrade"),
                            ("perpetual", "canPerpTrade"), ("prelievi", "canWithdraw"))
        if entry.get(flag, False)
    ]
    checks.append(Check(
        "permissions", "Permessi wallet API", OK if entry.get("canPerpTrade") else WARNING,
        f"Wallet API \"{entry.get('agentName', '-')}\" attivo. Permessi: {', '.join(granted)}.{expiry_note}"
        if entry.get("canPerpTrade") else
        f"Wallet API \"{entry.get('agentName', '-')}\" attivo ma senza permesso perpetual: "
        f"il venue perp non potrà operare. Permessi attuali: {', '.join(granted)}.{expiry_note}",
    ))

    # 5b. Identity: the account Aster resolves must be the one configured.
    try:
        accounts = await client.sub_accounts()
    except AsterError as exc:
        detail, code = _describe(exc)
        checks.append(Check("identity", "Identità account", WARNING, detail, code))
        accounts = None

    if accounts is not None:
        addresses = [
            str(a.get("address", ""))
            for a in (accounts if isinstance(accounts, list) else [])
            if a.get("address")
        ]
        match = next((a for a in addresses if a.lower() == account_address.lower()), None)
        if not addresses:
            checks.append(Check(
                "identity", "Identità account", WARNING,
                "Aster non restituisce alcun account per queste credenziali: "
                "impossibile confrontarlo con quello configurato.",
            ))
        elif match is None:
            checks.append(Check(
                "identity", "Identità account", CRITICAL,
                "L'account raggiunto da queste credenziali non è quello configurato "
                f"({short_address(addresses[0])} invece di {short_address(account_address)}). "
                "Le operazioni su Aster restano bloccate finché non viene risolto.",
            ))
            return finish(CRITICAL, "CONNESSIONE ASTER: ERRORE CRITICO", blocked=True)
        else:
            checks.append(Check(
                "identity", "Identità account", OK,
                f"Account confermato: {short_address(match)}.",
            ))

    # 6. Balance
    try:
        balances = await client.balance()
        funded = [
            b for b in (balances if isinstance(balances, list) else [])
            if _as_float(b.get("balance")) > 0
        ]
        detail = f"Saldo leggibile: {len(funded)} asset con disponibilità." if funded else \
            "Saldo leggibile, al momento nessun asset con disponibilità."
        checks.append(Check("balance", "Saldo", OK if funded else WARNING, detail))
    except AsterError as exc:
        if _looks_unfunded(exc):
            checks.append(Check("balance", "Saldo", WARNING, _UNFUNDED_DETAIL, exc.code))
        else:
            detail, code = _describe(exc)
            checks.append(Check("balance", "Saldo", ERROR, detail, code))

    # 7. Positions
    try:
        positions = await client.position_risk()
        open_positions = [
            p for p in (positions if isinstance(positions, list) else [])
            if _as_float(p.get("positionAmt")) != 0
        ]
        checks.append(Check(
            "positions", "Posizioni", OK,
            f"Posizioni leggibili: {len(open_positions)} aperte su Aster.",
        ))
    except AsterError as exc:
        if _looks_unfunded(exc):
            checks.append(Check("positions", "Posizioni", WARNING, _UNFUNDED_DETAIL, exc.code))
        else:
            detail, code = _describe(exc)
            checks.append(Check("positions", "Posizioni", ERROR, detail, code))

    # 8. Perp access + commission rate
    try:
        rate = await client.commission_rate("BTCUSDT")
        maker = rate.get("makerCommissionRate") if isinstance(rate, dict) else None
        taker = rate.get("takerCommissionRate") if isinstance(rate, dict) else None
        checks.append(Check(
            "perp", "Accesso Perpetual", OK,
            f"Perpetual accessibile. Commissioni dell'account: maker {maker}, taker {taker}."
            if maker is not None else "Perpetual accessibile.",
        ))
    except AsterError as exc:
        if _looks_unfunded(exc):
            checks.append(Check("perp", "Accesso Perpetual", WARNING, _UNFUNDED_DETAIL, exc.code))
        else:
            detail, code = _describe(exc)
            checks.append(Check("perp", "Accesso Perpetual", ERROR, detail, code))

    statuses = {c.status for c in checks}
    if CRITICAL in statuses:
        return finish(CRITICAL, "CONNESSIONE ASTER: ERRORE CRITICO", blocked=True)
    if ERROR in statuses:
        return finish(ERROR, "CONNESSIONE ASTER: ERRORE")
    if WARNING in statuses:
        return finish(WARNING, "CONNESSIONE ASTER: OPERATIVA CON AVVISI")

    return finish(OK, "CONNESSIONE ASTER: OPERATIVA")


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

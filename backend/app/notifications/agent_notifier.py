"""Sistema di notifiche push per eventi dell'agente autonomo."""

from __future__ import annotations

import json
from decimal import Decimal
from functools import lru_cache
from uuid import UUID

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.notifications.fcm.token_store import DeviceTokenStore
from backend.app.notifications.service import get_notification_service
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.notification_prefs import NotificationPreferences

logger = get_logger("notifications.agent_notifier")

_MAX_NOTIFIED_IDS = 500
_PRUNE_EVERY = 20


class AgentNotifier:
    """Notifiche push tipizzate per trade, rischio e riepilogo giornaliero."""

    PREFS_KEY = "notification_preferences"
    NOTIFIED_TRADES_KEY = "notified_trade_ids"
    RISK_STATE_KEY = "last_risk_notification"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._store = DeviceTokenStore(settings.fcm_token_store_path)
        self._append_count = 0

    # ------------------------------------------------------------------
    # Preferenze utente
    # ------------------------------------------------------------------

    def get_preferences(self, user_id: str) -> NotificationPreferences:
        """Legge da RuntimeState; fallback a default (tutto True)."""
        raw = get_runtime_value(user_id, self.PREFS_KEY)
        if raw:
            try:
                data = json.loads(raw)
                return NotificationPreferences(**data)
            except Exception:
                pass
        return NotificationPreferences()

    def set_preferences(self, user_id: str, prefs: NotificationPreferences) -> None:
        """Persiste in RuntimeState."""
        set_runtime_value(user_id, self.PREFS_KEY, json.dumps(prefs.model_dump()))

    # ------------------------------------------------------------------
    # Feed persistente (dashboard toast + timeline)
    # ------------------------------------------------------------------

    async def _record(
        self,
        user_id: str,
        category: str,
        severity: str,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
        link_type: str | None = None,
        link_ref: str | None = None,
    ) -> None:
        """Scrive l'evento nel feed notifiche (tabella notification_events).

        Degrada silenziosamente se il DB async non è inizializzato (es. in
        test unitari che non toccano la persistenza).
        """
        try:
            from backend.app.persistence.database import get_session_factory
            from backend.app.persistence.repositories.notifications import NotificationRepository

            factory = get_session_factory()
            async with factory() as session:
                repo = NotificationRepository(session)
                await repo.append(
                    user_id=user_id,
                    category=category,
                    severity=severity,
                    title=title,
                    body=body,
                    data_json=data,
                    link_type=link_type,
                    link_ref=link_ref,
                )
                self._append_count += 1
                if self._append_count % _PRUNE_EVERY == 0:
                    pruned = await repo.prune()
                    if pruned:
                        logger.info("notification_feed_pruned", deleted=pruned)
            from backend.app.notifications.feed_bus import notify as _bus_notify
            _bus_notify()
        except Exception as exc:
            logger.debug("notification_feed_record_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Notifiche trade
    # ------------------------------------------------------------------

    async def notify_trade_opened(
        self,
        user_id: str,
        trade_id: str,
        asset: str,
        market: str,
        direction: str,
        entry_price: Decimal,
        size_usd: Decimal,
        stop_loss: Decimal | None,
        is_dry_run: bool,
    ) -> bool:
        """Invia notifica apertura trade. Idempotente: salva trade_id in RuntimeState."""
        prefs = self.get_preferences(user_id)
        pref_key = "spot_trades" if market == "spot" else "perp_trades"
        if not getattr(prefs, pref_key, True):
            return False
        if is_dry_run and not self.settings.notify_dry_run_trades:
            return False
        if self._is_already_notified(user_id, trade_id):
            return False

        topic = (
            self.settings.fcm_spot_topic if market == "spot" else self.settings.fcm_perp_topic
        )
        dry_label = " [DRY]" if is_dry_run else ""
        sl_text = f" | SL {stop_loss:.4f}" if stop_loss else ""
        title = f"Trade aperto: {asset.upper()} {market.upper()}{dry_label}"
        body = (
            f"{direction.upper()} @ {entry_price:.4f} | Size ${size_usd:.2f}{sl_text}"
        )
        category = "spot_trade" if market == "spot" else "perp_trade"
        data = {
            "topic": topic,
            "trade_id": trade_id,
            "asset": asset,
            "market": market,
            "direction": direction,
            "entry_price": str(entry_price),
            "size_usd": str(size_usd),
            "dry_run": str(is_dry_run).lower(),
        }
        await self._record(
            user_id, category, "critical", title, body,
            data=data, link_type="trade", link_ref=f"{market}:{trade_id}",
        )
        sent = await self._send(
            user_id=user_id, title=title, body=body, severity="critical", data=data,
        )
        if sent:
            self._add_notified(user_id, trade_id)
        return sent

    async def notify_trade_closed(
        self,
        user_id: str,
        trade_id: str,
        asset: str,
        market: str,
        pnl_usd: Decimal,
        pnl_pct: Decimal,
        close_reason: str,
        is_dry_run: bool = False,
    ) -> bool:
        """Push ad alta priorità per chiusura posizione con PnL."""
        prefs = self.get_preferences(user_id)
        pref_key = "spot_trades" if market == "spot" else "perp_trades"
        if not getattr(prefs, pref_key, True):
            return False
        if is_dry_run and not self.settings.notify_dry_run_trades:
            return False

        topic = (
            self.settings.fcm_spot_topic if market == "spot" else self.settings.fcm_perp_topic
        )
        pnl_sign = "+" if pnl_usd >= 0 else ""
        title = f"Posizione chiusa: {asset.upper()} {market.upper()}"
        body = f"PnL {pnl_sign}{pnl_usd:.2f}$ ({pnl_sign}{pnl_pct:.2f}%) | {close_reason}"
        category = "spot_trade" if market == "spot" else "perp_trade"
        data = {
            "topic": topic,
            "trade_id": trade_id,
            "asset": asset,
            "market": market,
            "pnl_usd": str(pnl_usd),
            "pnl_pct": str(pnl_pct),
            "close_reason": close_reason,
        }
        await self._record(
            user_id, category, "critical", title, body,
            data=data, link_type="trade", link_ref=f"{market}:{trade_id}",
        )
        return await self._send(
            user_id=user_id, title=title, body=body, severity="critical", data=data,
        )

    # ------------------------------------------------------------------
    # Allarmi rischio
    # ------------------------------------------------------------------

    async def notify_risk_alert(
        self,
        user_id: str,
        alert_type: str,
        detail: str,
    ) -> bool:
        """Notifica allarme rischio con anti-spam (no ri-invio se stesso stato)."""
        prefs = self.get_preferences(user_id)
        if not prefs.risk_alerts:
            return False

        # Anti-spam: non inviare se stesso alert_type + detail già notificato
        last_raw = get_runtime_value(user_id, self.RISK_STATE_KEY)
        current_state = json.dumps({"alert_type": alert_type, "detail": detail})
        if last_raw == current_state:
            return False

        title = f"Allarme rischio: {alert_type.replace('_', ' ').title()}"
        body = detail
        data = {
            "topic": self.settings.fcm_risk_topic,
            "alert_type": alert_type,
            "detail": detail,
        }
        await self._record(user_id, "risk", "critical", title, body, data=data)
        sent = await self._send(
            user_id=user_id, title=title, body=body, severity="critical", data=data,
        )
        if sent:
            set_runtime_value(user_id, self.RISK_STATE_KEY, current_state)
        return sent

    # ------------------------------------------------------------------
    # Riepilogo giornaliero
    # ------------------------------------------------------------------

    async def notify_daily_summary(
        self,
        user_id: str,
        spot_trades: int,
        perp_trades: int,
        daily_pnl_usd: Decimal,
        win_rate_pct: float,
    ) -> bool:
        """Riepilogo giornaliero aggregato."""
        prefs = self.get_preferences(user_id)
        if not prefs.daily_summary:
            return False

        pnl_sign = "+" if daily_pnl_usd >= 0 else ""
        title = "Riepilogo giornaliero CryptoSentinel"
        body = (
            f"Spot {spot_trades} | Perp {perp_trades} | "
            f"PnL {pnl_sign}{daily_pnl_usd:.2f}$ | WR {win_rate_pct:.1f}%"
        )
        data = {
            "topic": self.settings.fcm_summary_topic,
            "spot_trades": str(spot_trades),
            "perp_trades": str(perp_trades),
            "daily_pnl_usd": str(daily_pnl_usd),
            "win_rate_pct": str(win_rate_pct),
        }
        await self._record(user_id, "summary", "info", title, body, data=data)
        return await self._send(
            user_id=user_id, title=title, body=body, severity="normal", data=data,
        )

    # ------------------------------------------------------------------
    # Eventi riserva "Bank"
    # ------------------------------------------------------------------

    _RESERVE_TITLES = {
        "sweep": "Riserva: sweep profitti",
        "deploy": "Riserva: deploy",
        "rebalance": "Riserva: ribilancio",
        "transfer": "Riserva: trasferimento",
    }

    async def notify_reserve_event(
        self,
        user_id: str,
        kind: str,
        detail: str,
        *,
        idempotency_key: str | None = None,
    ) -> bool:
        """Notifica un evento importante della riserva (D23). Opt-out via ``reserve_events``."""
        prefs = self.get_preferences(user_id)
        if not getattr(prefs, "reserve_events", True):
            return False
        if idempotency_key and self._is_already_notified(user_id, idempotency_key):
            return False

        title = self._RESERVE_TITLES.get(kind, "Riserva")
        data = {
            "topic": self.settings.fcm_summary_topic,
            "kind": kind,
            "detail": detail,
        }
        await self._record(user_id, "reserve", "normal", title, detail, data=data)
        sent = await self._send(
            user_id=user_id, title=title, body=detail, severity="normal", data=data,
        )
        if sent and idempotency_key:
            self._add_notified(user_id, idempotency_key)
        return sent

    # ------------------------------------------------------------------
    # Evento critico agente
    # ------------------------------------------------------------------

    async def notify_agent_critical(
        self,
        user_id: str,
        event: str,
        detail: str,
    ) -> bool:
        """Evento critico (degraded, servizio giù)."""
        prefs = self.get_preferences(user_id)
        if not prefs.critical:
            return False

        title = f"Agente critico: {event}"
        body = detail
        data = {
            "topic": self.settings.fcm_critical_topic or "cryptosentinel-critical",
            "event": event,
            "detail": detail,
        }
        await self._record(user_id, "system", "critical", title, body, data=data)
        return await self._send(
            user_id=user_id, title=title, body=body, severity="critical", data=data,
        )

    # ------------------------------------------------------------------
    # Idempotenza trade
    # ------------------------------------------------------------------

    def _get_notified_set(self, user_id: str) -> set[str]:
        """Carica set trade_id già notificati da RuntimeState."""
        raw = get_runtime_value(user_id, self.NOTIFIED_TRADES_KEY)
        if raw:
            try:
                return set(json.loads(raw))
            except Exception:
                pass
        return set()

    def _is_already_notified(self, user_id: str, trade_id: str) -> bool:
        return trade_id in self._get_notified_set(user_id)

    def _add_notified(self, user_id: str, trade_id: str) -> None:
        """Aggiunge trade_id al set; mantiene massimo 500 entries (sliding window FIFO)."""
        raw = get_runtime_value(user_id, self.NOTIFIED_TRADES_KEY)
        current_list: list[str] = []
        if raw:
            try:
                current_list = json.loads(raw)
            except Exception:
                current_list = []
        if trade_id not in current_list:
            current_list.append(trade_id)
        # Tronca a _MAX_NOTIFIED_IDS mantenendo gli ultimi
        if len(current_list) > _MAX_NOTIFIED_IDS:
            current_list = current_list[-_MAX_NOTIFIED_IDS:]
        set_runtime_value(user_id, self.NOTIFIED_TRADES_KEY, json.dumps(current_list))

    # ------------------------------------------------------------------
    # Invio FCM
    # ------------------------------------------------------------------

    async def _send(
        self,
        user_id: str,
        title: str,
        body: str,
        severity: str,
        data: dict[str, str],
    ) -> bool:
        """Invia a tutti i token FCM dell'utente. Ritorna True se almeno uno inviato."""
        if not self.settings.fcm_enabled:
            logger.debug("fcm_disabled_skip", title=title, user_id=user_id)
            return False
        try:
            tokens = self._store.tokens_for_user(UUID(user_id))
        except Exception as exc:
            logger.warning("agent_notifier_token_fetch_failed", error=str(exc))
            return False
        if not tokens:
            logger.debug("no_fcm_tokens", user_id=user_id)
            return False

        svc = get_notification_service()
        try:
            result = svc.fcm.send(
                tokens=tokens,
                title=title,
                body=body,
                severity=severity,  # type: ignore[arg-type]
                data={k: str(v) for k, v in data.items()},
            )
            sent = result.success_count > 0
            logger.info(
                "agent_notifier_sent",
                title=title,
                user_id=user_id,
                success=result.success_count,
                failure=result.failure_count,
                status=result.status,
            )
            return sent
        except Exception as exc:
            logger.warning("agent_notifier_send_failed", error=str(exc), title=title)
            return False


@lru_cache
def get_agent_notifier() -> AgentNotifier:
    """Singleton cached dell'AgentNotifier."""
    return AgentNotifier(get_settings())

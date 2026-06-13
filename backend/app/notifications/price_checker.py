"""Background task: fetches prices every minute and fires FCM when alerts trigger."""

from __future__ import annotations

import asyncio
import time

from backend.app.core.logging import get_logger
from backend.app.data.market_data.base import ProviderError
from backend.app.data.market_data.registry import MarketDataRegistry, get_market_data_registry
from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID
from backend.app.notifications.alert_store import get_alert_store
from backend.app.notifications.service import get_notification_service
from backend.app.schemas.alerts import PendingFavAlert

logger = get_logger("notifications.price_checker")

CHECK_INTERVAL_S = 60
RANGE_COOLDOWN_MS = 5 * 60 * 1000


def _fmt(v: float) -> str:
    if v >= 1000:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:.2f}"
    return f"{v:.6f}"


def _price_key(coin_id: str, direction: str, threshold: float) -> str:
    return f"{coin_id}:{direction}:{threshold}"


async def _fetch_prices(
    coin_ids: list[str],
    vs_currencies: list[str],
    registry: MarketDataRegistry | None = None,
) -> dict[str, dict[str, float]]:
    selected_registry = registry or get_market_data_registry()
    try:
        quotes = await selected_registry.get_prices(coin_ids, vs_currencies)
        prices: dict[str, dict[str, float]] = {}
        for quote in quotes:
            prices.setdefault(quote.asset_id, {})[quote.currency] = quote.price
        return prices
    except ProviderError as exc:
        logger.warning(
            "market_data_fetch_failed",
            provider=selected_registry.active_name.value,
            error=str(exc),
        )
        return {}


async def run_price_check(registry: MarketDataRegistry | None = None) -> None:
    """Single price-check tick."""
    store = get_alert_store()
    config = store.get_config()
    if config is None:
        return

    coin_ids: list[str] = []
    vs: set[str] = {"usd"}
    if config.fav_currency and config.fav_currency.lower() != "usd":
        vs.add(config.fav_currency.lower())

    for a in config.price_alerts:
        if a.coin_id not in coin_ids:
            coin_ids.append(a.coin_id)
    for a in config.range_alerts:
        if a.coin_id not in coin_ids:
            coin_ids.append(a.coin_id)
    has_fav = (config.fav_up_pct > 0 or config.fav_down_pct > 0) and bool(config.fav_coins)
    if has_fav:
        for c in config.fav_coins:
            if c.id not in coin_ids:
                coin_ids.append(c.id)

    if not coin_ids:
        return

    prices = await _fetch_prices(coin_ids, list(vs), registry)
    if not prices:
        return

    svc = get_notification_service()
    tokens = svc.store.tokens_for_user(DEFAULT_SINGLE_USER_ID)
    if not tokens:
        return

    state = store.get_state()
    now_ms = time.time() * 1000
    state_changed = False

    # --- Price alerts (one-shot) ---
    for alert in config.price_alerts:
        key = _price_key(alert.coin_id, alert.direction, alert.threshold)
        if key in state.triggered_keys:
            continue
        price = prices.get(alert.coin_id, {}).get("usd", -1.0)
        if price < 0:
            continue
        fire = (alert.direction == "above" and price >= alert.threshold) or \
               (alert.direction == "below" and price <= alert.threshold)
        if not fire:
            continue
        arrow = "▲" if alert.direction == "above" else "▼"
        label = "superato al rialzo" if alert.direction == "above" else "superato al ribasso"
        title = f"{arrow} {alert.coin_name} — soglia {label}"
        body = f"Soglia: ${_fmt(alert.threshold)}  ·  Prezzo: ${_fmt(price)}"
        if alert.note:
            body += f"\n📝 {alert.note}"
        svc.fcm.send(
            tokens=tokens, title=title, body=body, severity="critical",
            data={"type": "price_alert", "coin_id": alert.coin_id},
        )
        state.triggered_keys.add(key)
        state_changed = True
        logger.info("fcm_price_alert_fired", coin=alert.coin_id, direction=alert.direction, price=price)

    # --- Range alerts (repeating with cooldown) ---
    for alert in config.range_alerts:
        alert_id = f"{alert.coin_id}:{alert.min_price}:{alert.max_price}"
        price = prices.get(alert.coin_id, {}).get("usd", -1.0)
        if price < 0:
            continue
        is_inside = alert.min_price <= price <= alert.max_price
        was_inside = state.range_is_inside.get(alert_id)
        state.range_is_inside[alert_id] = is_inside
        if was_inside is None:
            state_changed = True
            continue
        if is_inside == was_inside:
            continue
        if now_ms - state.range_last_notified.get(alert_id, 0.0) < RANGE_COOLDOWN_MS:
            continue
        status_label = "↔ Entrato nel range" if is_inside else "↗ Uscito dal range"
        title = f"{status_label} — {alert.coin_name}"
        body = f"Range: ${_fmt(alert.min_price)} – ${_fmt(alert.max_price)}  ·  Ora: ${_fmt(price)}"
        if alert.note:
            body += f"\n📝 {alert.note}"
        svc.fcm.send(
            tokens=tokens, title=title, body=body, severity="critical",
            data={"type": "range_alert", "coin_id": alert.coin_id},
        )
        state.range_last_notified[alert_id] = now_ms
        state_changed = True
        logger.info("fcm_range_alert_fired", coin=alert.coin_id, inside=is_inside, price=price)

    # --- Fav coin move alerts ---
    if has_fav:
        fav_currency = config.fav_currency.lower()
        for coin in config.fav_coins:
            coin_prices = prices.get(coin.id, {})
            current = coin_prices.get(fav_currency, coin_prices.get("usd", -1.0))
            if current < 0:
                continue
            ref = state.fav_ref_prices.get(coin.id)
            if ref is None or ref <= 0:
                state.fav_ref_prices[coin.id] = current
                state_changed = True
                continue
            pct = (current - ref) / ref * 100.0
            direction: str | None = None
            if config.fav_up_pct > 0 and pct >= config.fav_up_pct:
                direction = "up"
            elif config.fav_down_pct > 0 and pct <= -config.fav_down_pct:
                direction = "down"
            if direction is None:
                continue
            arrow = "▲" if direction == "up" else "▼"
            label = "rialzo" if direction == "up" else "ribasso"
            title = f"{arrow} {coin.name} ({coin.symbol.upper()}) — {label} del {abs(pct):.1f}%"
            body = f"Movimento del {abs(pct):.1f}% verso il {label}  ·  Ora: ${_fmt(current)}"
            delivery = svc.fcm.send(
                tokens=tokens, title=title, body=body, severity="critical",
                data={
                    "type": "fav_alert",
                    "coin_id": coin.id,
                    "coin_name": coin.name,
                    "coin_symbol": coin.symbol,
                    "direction": direction,
                    "pct": f"{abs(pct):.8f}",
                    "current_price": f"{current:.12f}",
                    "ref_price": f"{ref:.12f}",
                },
            )
            if delivery.success_count > 0:
                state.pending_fav_alerts[coin.id] = PendingFavAlert(
                    coin_id=coin.id,
                    coin_name=coin.name,
                    coin_symbol=coin.symbol,
                    direction=direction,
                    pct=abs(pct),
                    current_price=current,
                    ref_price=ref,
                )
            state.fav_ref_prices[coin.id] = current
            state_changed = True
            logger.info("fcm_fav_alert_fired", coin=coin.id, direction=direction, pct=round(abs(pct), 2))

    if state_changed:
        store.update_state(state)


async def price_checker_loop() -> None:
    """Run price checks indefinitely every CHECK_INTERVAL_S seconds."""
    logger.info("price_checker_started", interval_s=CHECK_INTERVAL_S)
    while True:
        try:
            await run_price_check()
        except Exception as exc:
            logger.warning("price_checker_error", error=str(exc))
        await asyncio.sleep(CHECK_INTERVAL_S)

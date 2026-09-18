"""Alert synchronization routes."""

import anyio
from fastapi import APIRouter

from backend.app.api.dependencies import AlertsAccessDep
from backend.app.notifications.alert_store import get_alert_store
from backend.app.schemas.alerts import (
    AlertSyncRequest,
    AlertSyncResponse,
    PendingFavAlert,
    PendingFavAlertsResponse,
)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/sync")
async def sync_alerts(
    request: AlertSyncRequest,
    _: AlertsAccessDep,
) -> AlertSyncResponse:
    """Store the latest alert thresholds from one device.

    The per-device store keeps each phone's alerts separate; tokens without a
    device_id fall back to the legacy global store.
    """
    await anyio.to_thread.run_sync(_save_alert_config, request)
    return AlertSyncResponse(
        status="synced",
        price_alert_count=len(request.price_alerts),
        range_alert_count=len(request.range_alerts),
        fav_coin_count=len(request.fav_coins),
    )


@router.get("/pending-favorites")
async def pending_favorite_alerts(
    _: AlertsAccessDep,
    device_id: str | None = None,
) -> PendingFavAlertsResponse:
    """Return favorite alerts awaiting explicit acknowledgement on this device."""

    items = await anyio.to_thread.run_sync(_pending_fav_alerts, device_id)
    return PendingFavAlertsResponse(items=items)


@router.delete("/pending-favorites/{coin_id}")
async def dismiss_pending_favorite_alert(
    coin_id: str,
    _: AlertsAccessDep,
    device_id: str | None = None,
) -> dict[str, str]:
    """Acknowledge one favorite alert and remove its persisted badge state."""

    removed = await anyio.to_thread.run_sync(_dismiss_pending_fav_alert, device_id, coin_id)
    return {"status": "dismissed" if removed else "not_found"}


def _save_alert_config(request: AlertSyncRequest) -> None:
    get_alert_store(request.device_id).save_config(request)


def _pending_fav_alerts(device_id: str | None) -> list[PendingFavAlert]:
    return get_alert_store(device_id).pending_fav_alerts()


def _dismiss_pending_fav_alert(device_id: str | None, coin_id: str) -> bool:
    return get_alert_store(device_id).dismiss_pending_fav_alert(coin_id)

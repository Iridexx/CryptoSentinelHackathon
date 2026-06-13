"""Alert synchronization routes."""

from fastapi import APIRouter

from backend.app.api.dependencies import AlertsAccessDep
from backend.app.notifications.alert_store import get_alert_store
from backend.app.schemas.alerts import AlertSyncRequest, AlertSyncResponse, PendingFavAlertsResponse

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/sync")
async def sync_alerts(
    request: AlertSyncRequest,
    _: AlertsAccessDep,
) -> AlertSyncResponse:
    """Store the latest alert thresholds from the mobile app."""
    get_alert_store().save_config(request)
    return AlertSyncResponse(
        status="synced",
        price_alert_count=len(request.price_alerts),
        range_alert_count=len(request.range_alerts),
        fav_coin_count=len(request.fav_coins),
    )


@router.get("/pending-favorites")
async def pending_favorite_alerts(_: AlertsAccessDep) -> PendingFavAlertsResponse:
    """Return favorite alerts awaiting explicit acknowledgement in the app."""

    return PendingFavAlertsResponse(items=get_alert_store().pending_fav_alerts())


@router.delete("/pending-favorites/{coin_id}")
async def dismiss_pending_favorite_alert(coin_id: str, _: AlertsAccessDep) -> dict[str, str]:
    """Acknowledge one favorite alert and remove its persisted badge state."""

    removed = get_alert_store().dismiss_pending_fav_alert(coin_id)
    return {"status": "dismissed" if removed else "not_found"}

"""Alert synchronization routes."""

from fastapi import APIRouter

from backend.app.api.dependencies import AlertsAccessDep
from backend.app.notifications.alert_store import get_alert_store
from backend.app.schemas.alerts import AlertSyncRequest, AlertSyncResponse

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

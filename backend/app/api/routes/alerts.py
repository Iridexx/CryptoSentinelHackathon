"""Alert sync and test routes."""

from pydantic import BaseModel

from fastapi import APIRouter

from backend.app.api.dependencies import DeviceAccessDep
from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID
from backend.app.notifications.alert_store import get_alert_store
from backend.app.notifications.service import get_notification_service
from backend.app.schemas.alerts import AlertSyncRequest, AlertSyncResponse

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.post("/sync")
async def sync_alerts(
    request: AlertSyncRequest,
    _: DeviceAccessDep,
) -> AlertSyncResponse:
    """Store the latest alert thresholds from the mobile app."""
    get_alert_store().save_config(request)
    return AlertSyncResponse(
        status="synced",
        price_alert_count=len(request.price_alerts),
        range_alert_count=len(request.range_alerts),
        fav_coin_count=len(request.fav_coins),
    )


class NotifTestResponse(BaseModel):
    status: str
    device_count: int
    reason: str | None = None


@router.post("/test-notification")
async def test_notification(_: DeviceAccessDep) -> NotifTestResponse:
    """Send a test FCM push notification to all registered devices."""
    svc = get_notification_service()
    tokens = svc.store.tokens_for_user(DEFAULT_SINGLE_USER_ID)
    if not tokens:
        return NotifTestResponse(status="skipped", device_count=0, reason="no_registered_devices")
    if not svc.fcm.configured:
        return NotifTestResponse(status="skipped", device_count=0, reason="fcm_not_configured")
    result = svc.fcm.send(
        tokens=tokens,
        title="🔔 CryptoSentinel — Test notifica",
        body="Il sistema di notifiche FCM funziona correttamente.",
        severity="critical",
        data={"type": "test"},
    )
    return NotifTestResponse(
        status=result.status,
        device_count=result.success_count,
        reason=None if result.status == "sent" else result.status,
    )

"""Notification routes."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies import AdminAccessDep, DeviceAccessDep, ReadAccessDep, SessionDep, SettingsDep
from backend.app.notifications.service import NotificationService, get_notification_service
from backend.app.persistence.repositories.notifications import NotificationRepository
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.notifications import (
    DeviceListResponse,
    DeviceRecord,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    DeviceUnregisterRequest,
    FeedEventItem,
    FeedReadRequest,
    FeedReadResponse,
    FeedResponse,
    NotificationRequest,
    NotificationSendResponse,
    NotificationStatusResponse,
    ToastPreferences,
    ToastPreferencesResponse,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/status")
async def notification_status(
    _: ReadAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationStatusResponse:
    """Return FCM subsystem status."""

    return service.status()


@router.get("/devices")
async def list_devices(
    _: AdminAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> DeviceListResponse:
    """List all registered device tokens (no raw FCM token exposed)."""

    records = service.list_devices()
    return DeviceListResponse(
        devices=[
            DeviceRecord(
                token_id=r.token_id,
                platform=r.platform,
                device_id=r.device_id,
                app_version=r.app_version,
                display_name=r.display_name,
                locale=r.locale,
                registered_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in records
        ],
        total=len(records),
    )


@router.post("/devices", status_code=201)
async def register_device(
    request: DeviceRegistrationRequest,
    _: DeviceAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> DeviceRegistrationResponse:
    """Register a device token for server-side notifications."""

    return service.register_device(request)


@router.post("/devices/unregister")
async def unregister_device(
    request: DeviceUnregisterRequest,
    _: DeviceAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> DeviceRegistrationResponse:
    """Remove a device token from the registry."""

    return service.unregister_device(request)


@router.post("/send")
async def send_notification(
    request: NotificationRequest,
    _: AdminAccessDep,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationSendResponse:
    """Send a server-side notification via FCM."""

    return service.send(request)


# ---------------------------------------------------------------------------
# Dashboard notification feed  (plans/Plan_Notifiche.md, fase 3)
# ---------------------------------------------------------------------------

TOAST_PREFS_KEY = "toast_preferences"


def _event_to_item(evt) -> FeedEventItem:
    return FeedEventItem(
        event_id=evt.event_id,
        category=evt.category,
        severity=evt.severity,
        title=evt.title,
        body=evt.body,
        data=evt.data_json,
        link_type=evt.link_type,
        link_ref=evt.link_ref,
        created_at=evt.created_at.isoformat(),
        read_at=evt.read_at.isoformat() if evt.read_at else None,
    )


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    _: ReadAccessDep,
    session: SessionDep,
    since: str | None = None,
    before: str | None = None,
    categories: str | None = Query(None, description="Comma-separated category filter"),
    severities: str | None = Query(None, description="Comma-separated severity filter"),
    unread_only: bool = False,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> FeedResponse:
    """Feed notifiche per il dashboard — supporta cursori since/before."""

    repo = NotificationRepository(session)
    cat_list = [c.strip() for c in categories.split(",")] if categories else None
    sev_list = [s.strip() for s in severities.split(",")] if severities else None

    items = await repo.list(
        since=since,
        before=before,
        categories=cat_list,
        severities=sev_list,
        unread_only=unread_only,
        q=q,
        limit=limit,
    )
    unread = await repo.unread_count()
    cursor = items[-1].event_id if items else None
    return FeedResponse(
        items=[_event_to_item(e) for e in items],
        unread_count=unread,
        cursor=cursor,
    )


@router.get("/feed/stream")
async def feed_stream(
    request: Request,
    _: ReadAccessDep,
    since: str | None = None,
):
    """SSE stream: emette un evento ogni volta che arriva una nuova notifica."""
    from backend.app.notifications.feed_bus import listen
    from backend.app.persistence.database import get_session_factory

    async def _generate():
        cursor = since
        with listen() as wake:
            while True:
                if await request.is_disconnected():
                    break
                factory = get_session_factory()
                async with factory() as session:
                    repo = NotificationRepository(session)
                    items = await repo.list(since=cursor, limit=50)
                    unread = await repo.unread_count()

                if items:
                    cursor = items[-1].event_id
                    payload = json.dumps({
                        "items": [_event_to_item(e).model_dump() for e in items],
                        "unread_count": unread,
                        "cursor": cursor,
                    })
                    yield f"data: {payload}\n\n"
                else:
                    yield f": keepalive\n\n"

                wake.clear()
                try:
                    await asyncio.wait_for(wake.wait(), timeout=30.0)
                except asyncio.TimeoutError:
                    pass

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feed/read", response_model=FeedReadResponse)
async def mark_feed_read(
    request: FeedReadRequest,
    _: ReadAccessDep,
    session: SessionDep,
) -> FeedReadResponse:
    """Segna come lette le notifiche specificate (per id o tutte)."""

    repo = NotificationRepository(session)
    unread = await repo.mark_read(
        ids=request.ids,
        all=request.all,
        before=request.before,
    )
    return FeedReadResponse(unread_count=unread)


@router.get("/toast-prefs", response_model=ToastPreferencesResponse)
async def get_toast_prefs(
    _: ReadAccessDep,
    settings: SettingsDep,
) -> ToastPreferencesResponse:
    """Preferenze toast per categoria (quali notifiche mostrano il toast nel dashboard)."""

    user_id = str(settings.default_user_id)
    raw = get_runtime_value(user_id, TOAST_PREFS_KEY)
    if raw:
        try:
            prefs = ToastPreferences(**json.loads(raw))
            return ToastPreferencesResponse(preferences=prefs, source="persisted")
        except Exception:
            pass
    return ToastPreferencesResponse(preferences=ToastPreferences(), source="default")


@router.put("/toast-prefs", response_model=ToastPreferencesResponse)
async def update_toast_prefs(
    request: ToastPreferences,
    _: ReadAccessDep,
    settings: SettingsDep,
) -> ToastPreferencesResponse:
    """Salva le preferenze toast per categoria."""

    user_id = str(settings.default_user_id)
    set_runtime_value(user_id, TOAST_PREFS_KEY, json.dumps(request.model_dump()))
    return ToastPreferencesResponse(preferences=request, source="persisted")

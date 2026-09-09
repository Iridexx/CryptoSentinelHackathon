"""Notification schemas."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID

NotificationSeverity = Literal["critical", "warning", "info"]
DevicePlatform = Literal["android", "ios", "web"]


class DeviceRegistrationRequest(BaseModel):
    """Register a client device token for server-side notifications."""

    token: str = Field(min_length=16)
    platform: DevicePlatform = "android"
    user_id: UUID = DEFAULT_SINGLE_USER_ID
    device_id: str | None = None
    app_version: str | None = None
    build_number: str | None = None
    locale: str | None = None
    display_name: str | None = Field(default=None, max_length=120)


class DeviceUnregisterRequest(BaseModel):
    """Unregister a client device token."""

    token: str = Field(min_length=16)
    user_id: UUID = DEFAULT_SINGLE_USER_ID


class DeviceRegistrationResponse(BaseModel):
    """Device registration result."""

    status: Literal["registered", "removed"]
    token_id: str
    user_id: UUID


class NotificationRequest(BaseModel):
    """Server-side notification request."""

    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=500)
    severity: NotificationSeverity = "info"
    user_id: UUID = DEFAULT_SINGLE_USER_ID
    data: dict[str, str] = Field(default_factory=dict)
    token_ids: list[str] | None = None
    dry_run: bool = False


class NotificationSendResponse(BaseModel):
    """Notification send result."""

    status: Literal["sent", "partial", "skipped", "failed"]
    severity: NotificationSeverity
    requested_tokens: int
    success_count: int
    failure_count: int
    skipped_reason: str | None = None
    message_ids: list[str] = Field(default_factory=list)


class NotificationStatusResponse(BaseModel):
    """Notification subsystem status."""

    enabled: bool
    configured: bool
    token_count: int
    critical_topic: str | None
    token_store_path: str
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DeviceRecord(BaseModel):
    """Public view of a registered device — no raw FCM token."""

    token_id: str
    platform: str
    device_id: str | None
    app_version: str | None
    display_name: str | None = None
    locale: str | None
    registered_at: str
    updated_at: str


class DeviceListResponse(BaseModel):
    """List of registered devices."""

    devices: list[DeviceRecord]
    total: int


# ---------------------------------------------------------------------------
# Dashboard notification feed (plans/Plan_Notifiche.md)
# ---------------------------------------------------------------------------


class FeedEventItem(BaseModel):
    """Singola riga del feed notifiche dashboard."""

    event_id: str
    category: str
    severity: str
    title: str
    body: str
    data: dict | None = None
    link_type: str | None = None
    link_ref: str | None = None
    created_at: str
    read_at: str | None = None


class FeedResponse(BaseModel):
    """Risposta GET /feed."""

    items: list[FeedEventItem]
    unread_count: int
    cursor: str | None = None


class FeedReadRequest(BaseModel):
    """Corpo POST /feed/read — segna come letti."""

    ids: list[str] | None = None
    all: bool = False
    before: str | None = None


class FeedReadResponse(BaseModel):
    """Risposta POST /feed/read."""

    unread_count: int


class ToastPreferences(BaseModel):
    """Flag per categoria: il toast compare nel dashboard?"""

    toast_spot_trade: bool = True
    toast_perp_trade: bool = True
    toast_risk: bool = True
    toast_system: bool = True
    toast_reserve: bool = False
    toast_summary: bool = False


class ToastPreferencesResponse(BaseModel):
    """Risposta GET/PUT /toast-prefs."""

    preferences: ToastPreferences
    source: str  # "default" | "persisted"

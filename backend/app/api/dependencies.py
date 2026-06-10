"""FastAPI dependency helpers."""

from typing import Annotated

from fastapi import Depends, Request

from backend.app.core.config import Settings, get_settings
from backend.app.core.security.auth import AuthScope, require_scope

SettingsDep = Annotated[Settings, Depends(get_settings)]


def require_read_access(request: Request, settings: SettingsDep) -> AuthScope:
    """Require read or admin API token."""

    return require_scope(request, settings, AuthScope.READ)


def require_admin_access(request: Request, settings: SettingsDep) -> AuthScope:
    """Require admin API token."""

    return require_scope(request, settings, AuthScope.ADMIN)


def require_device_access(request: Request, settings: SettingsDep) -> AuthScope:
    """Require device registration or admin API token."""

    return require_scope(request, settings, AuthScope.DEVICE)

ReadAccessDep = Annotated[AuthScope, Depends(require_read_access)]
AdminAccessDep = Annotated[AuthScope, Depends(require_admin_access)]
DeviceAccessDep = Annotated[AuthScope, Depends(require_device_access)]

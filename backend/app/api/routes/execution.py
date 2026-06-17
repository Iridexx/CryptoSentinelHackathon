"""Execution-layer status and competition checks."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep
from backend.app.execution.registry import (
    ExecutionProviderRegistry,
    get_execution_provider_registry,
)
from backend.app.execution.service import ExecutionService, get_execution_service
from backend.app.schemas.execution import (
    ExecutionProviderSelectionRequest,
    ExecutionProviderSelectionResponse,
)

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])
ExecutionServiceDep = Annotated[ExecutionService, Depends(get_execution_service)]
RegistryDep = Annotated[ExecutionProviderRegistry, Depends(get_execution_provider_registry)]


@router.get("/status")
async def execution_status(
    service: ExecutionServiceDep,
    _: ReadAccessDep,
) -> dict[str, Any]:
    """Return non-sensitive execution readiness."""

    return service.status()


@router.get("/provider", response_model=ExecutionProviderSelectionResponse)
async def execution_provider_status(
    registry: RegistryDep,
    _: ReadAccessDep,
) -> ExecutionProviderSelectionResponse:
    """Return the global spot execution provider selection and diagnostics."""

    return ExecutionProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
    )


@router.put("/provider", response_model=ExecutionProviderSelectionResponse)
async def select_execution_provider(
    request: ExecutionProviderSelectionRequest,
    registry: RegistryDep,
    _: AdminAccessDep,
) -> ExecutionProviderSelectionResponse:
    """Select one global spot execution provider until restart. No fallback."""

    registry.select(request.provider)
    return ExecutionProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
    )


@router.get("/competition/status")
async def competition_status(
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> dict[str, Any]:
    """Verify competition registration directly against the configured contract."""

    return await service.competition_registration_status()


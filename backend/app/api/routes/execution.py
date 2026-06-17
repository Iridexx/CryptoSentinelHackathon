"""Execution-layer status and competition checks."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep
from backend.app.execution.service import ExecutionService, get_execution_service

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])
ExecutionServiceDep = Annotated[ExecutionService, Depends(get_execution_service)]


@router.get("/status")
async def execution_status(
    service: ExecutionServiceDep,
    _: ReadAccessDep,
) -> dict[str, Any]:
    """Return non-sensitive execution readiness."""

    return service.status()


@router.get("/competition/status")
async def competition_status(
    service: ExecutionServiceDep,
    _: AdminAccessDep,
) -> dict[str, Any]:
    """Verify competition registration directly against the configured contract."""

    return await service.competition_registration_status()


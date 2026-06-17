"""API schemas for the execution-provider selectors (spot and perp)."""

from pydantic import BaseModel, Field

from backend.app.execution.base import ExecutionProviderName, ExecutionProviderStatus
from backend.app.execution.perp_base import (
    PerpExecutionProviderName,
    PerpProviderStatus,
)


class ExecutionProviderSelectionRequest(BaseModel):
    provider: ExecutionProviderName


class ExecutionProviderSelectionResponse(BaseModel):
    active: ExecutionProviderName
    providers: list[ExecutionProviderStatus]
    selection_scope: str = Field(
        default="process",
        description="Selection resets to config on restart unless persisted in RuntimeState.",
    )


class PerpProviderSelectionRequest(BaseModel):
    provider: PerpExecutionProviderName


class PerpProviderSelectionResponse(BaseModel):
    active: PerpExecutionProviderName
    providers: list[PerpProviderStatus]
    selection_scope: str = Field(
        default="process",
        description="Selection resets to config on restart unless persisted in RuntimeState.",
    )

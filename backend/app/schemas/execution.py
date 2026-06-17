"""API schemas for the execution-provider selector."""

from pydantic import BaseModel, Field

from backend.app.execution.base import ExecutionProviderName, ExecutionProviderStatus


class ExecutionProviderSelectionRequest(BaseModel):
    provider: ExecutionProviderName


class ExecutionProviderSelectionResponse(BaseModel):
    active: ExecutionProviderName
    providers: list[ExecutionProviderStatus]
    selection_scope: str = Field(
        default="process",
        description="Selection resets to config on restart unless persisted in RuntimeState.",
    )

"""Agent Step 6 status, kill-switch and dry-run evaluation routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.agent.risk import KillSwitchState
from backend.app.agent.service import get_agent_service
from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class KillSwitchRequest(BaseModel):
    state: Literal["running", "soft_stop", "hard_stop", "degraded"]


class AgentEvaluateRequest(BaseModel):
    market: Literal["spot", "perp"]
    payload: dict[str, Any] = Field(default_factory=dict)


@router.get("/status")
async def agent_status(_: ReadAccessDep) -> dict:
    """Return non-sensitive agent status."""

    return get_agent_service().status()


@router.put("/kill-switch")
async def set_kill_switch(request: KillSwitchRequest, _: AdminAccessDep) -> dict:
    """Set the process-level agent kill switch."""

    return get_agent_service().set_kill_switch(KillSwitchState(request.state))


@router.post("/evaluate")
async def evaluate_signal(request: AgentEvaluateRequest, _: AdminAccessDep, session: SessionDep) -> dict:
    """Evaluate an explicit signal payload through signal, risk and brain layers."""

    service = get_agent_service()
    try:
        if request.market == "spot":
            return await service.evaluate_spot(request.payload, session)
        return await service.evaluate_perp(request.payload, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

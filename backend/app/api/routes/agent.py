"""Agent Step 6 status, kill-switch and dry-run evaluation routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agent.risk import KillSwitchState
from backend.app.agent.service import get_agent_service
from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class KillSwitchRequest(BaseModel):
    state: Literal["running", "soft_stop", "hard_stop", "degraded"]


class AgentEvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    market: Literal["spot", "perp"]
    payload: dict[str, Any] = Field(default_factory=dict)

    def normalized_payload(self) -> dict[str, Any]:
        """Accept both nested payloads and the legacy flat evaluation body."""

        normalized = dict(self.payload)
        for key, value in (self.model_extra or {}).items():
            normalized.setdefault(key, value)
        return normalized


@router.get("/status")
async def agent_status(_: ReadAccessDep) -> dict:
    """Return non-sensitive agent status."""

    return get_agent_service().status()


@router.get("/data-coverage")
async def agent_data_coverage(_: ReadAccessDep) -> dict:
    """Return OHLCV cache coverage for agent signal engines."""

    return get_agent_service().data_coverage()


@router.put("/kill-switch")
async def set_kill_switch(request: KillSwitchRequest, _: AdminAccessDep) -> dict:
    """Set the process-level agent kill switch."""

    return get_agent_service().set_kill_switch(KillSwitchState(request.state))


@router.post("/evaluate")
async def evaluate_signal(request: AgentEvaluateRequest, _: AdminAccessDep, session: SessionDep) -> dict:
    """Evaluate an explicit signal payload through signal, risk and brain layers."""

    service = get_agent_service()
    payload = request.normalized_payload()
    try:
        if request.market == "spot":
            return await service.evaluate_spot(payload, session)
        return await service.evaluate_perp(payload, session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

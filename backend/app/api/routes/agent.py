"""Agent Step 6 status, kill-switch and dry-run evaluation routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.agent.risk import KillSwitchState
from backend.app.agent.service import get_agent_service
from backend.app.agent.watchlist import selected_watchlist, set_selected_watchlist
from backend.app.agent.ohlcv_warmup import warmup_selected_watchlist
from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


class KillSwitchRequest(BaseModel):
    state: Literal["running", "soft_stop", "hard_stop", "degraded"]


class AgentWatchlistRequest(BaseModel):
    tokens: list[str] = Field(default_factory=list)


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


@router.get("/eligible-tokens")
async def agent_eligible_tokens(_: ReadAccessDep) -> dict:
    """Return the configured tradable token universe for client UI gating."""

    service = get_agent_service()
    return {
        "count": len(service.settings.eligible_tokens),
        "tokens": service.settings.eligible_tokens,
    }


@router.get("/watchlist")
async def agent_watchlist(_: ReadAccessDep) -> dict:
    """Return the eligible universe and the operational agent watchlist."""

    service = get_agent_service()
    selected = selected_watchlist(service.settings)
    return {
        "eligible_count": len(service.settings.eligible_tokens),
        "eligible_tokens": service.settings.eligible_tokens,
        "selected_count": len(selected),
        "selected_tokens": selected,
    }


@router.put("/watchlist")
async def set_agent_watchlist(request: AgentWatchlistRequest, _: AdminAccessDep) -> dict:
    """Persist the operational agent watchlist."""

    service = get_agent_service()
    previous = set(selected_watchlist(service.settings))
    try:
        selected = set_selected_watchlist(service.settings, request.tokens)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    added = [token for token in selected if token not in previous]
    warmup = await warmup_selected_watchlist(service.settings, assets=added) if added else {
        "status": "skipped",
        "reason": "no_new_tokens",
        "items": [],
    }
    return {
        "eligible_count": len(service.settings.eligible_tokens),
        "eligible_tokens": service.settings.eligible_tokens,
        "selected_count": len(selected),
        "selected_tokens": selected,
        "warmup": warmup,
    }


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

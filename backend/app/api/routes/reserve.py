"""API for the "Bank" store-of-value reserve (plans/Plan_Reserve.md, R5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SessionDep
from backend.app.core.config import get_settings
from backend.app.core.logging import get_logger
from backend.app.domain.reserve import (
    ReserveError,
    ReserveExecutionError,
    load_reserve_settings,
    save_reserve_settings,
)
from backend.app.domain.reserve.pricing import build_reserve_service
from backend.app.persistence.repositories.reserve import ReserveRepository
from backend.app.schemas.reserve import (
    ReserveSettings,
    ReserveSettingsResponse,
    ReserveView,
)

logger = get_logger("api.reserve")

router = APIRouter(prefix="/api/v1/agent/reserve", tags=["reserve"])

_RANGE_DAYS = {"24h": 1, "7d": 7, "all": None}


def _user_id() -> str:
    return str(get_settings().default_user_id)


def _domain_error(exc: ReserveError) -> HTTPException:
    return HTTPException(status_code=400, detail=exc.code)


# ── requests ─────────────────────────────────────────────────────────────────


class TransferRequest(BaseModel):
    amount_usd: float = Field(..., gt=0)
    direction: Literal["in", "out"]


class TargetWeightsRequest(BaseModel):
    weights: dict[str, float]


class RebalanceRequest(BaseModel):
    dry_run: bool = False


# ── reads ────────────────────────────────────────────────────────────────────


@router.get("", response_model=ReserveView)
async def get_reserve(_: ReadAccessDep, session: SessionDep) -> ReserveView:
    settings = get_settings()
    service = await build_reserve_service(session, settings)
    try:
        return await service.get_view(_user_id())
    except ReserveExecutionError:
        raise HTTPException(status_code=503, detail="price_unavailable")


@router.get("/history")
async def get_history(
    _: ReadAccessDep,
    session: SessionDep,
    range: Literal["24h", "7d", "all"] = Query("7d"),
) -> dict:
    repo = ReserveRepository(session)
    days = _RANGE_DAYS[range]
    if days is None:
        rows = list(reversed(await repo.recent_snapshots(_user_id(), limit=2000)))
    else:
        rows = await repo.snapshots_since(_user_id(), datetime.now(UTC) - timedelta(days=days))
    items = [
        {
            "timestamp_utc": s.timestamp_utc.isoformat(),
            "total_value_usd": str(s.total_value_usd),
            "cash_usd": str(s.cash_usd),
            "cost_basis_usd": str(s.cost_basis_usd),
            "pnl_usd": str(s.pnl_usd),
            "fees_cumulative_usd": str(s.fees_cumulative_usd),
        }
        for s in rows
    ]
    return {"range": range, "items": items, "count": len(items)}


@router.get("/settings", response_model=ReserveSettingsResponse)
async def get_settings_endpoint(_: ReadAccessDep) -> ReserveSettingsResponse:
    return load_reserve_settings(_user_id())


# ── admin actions ────────────────────────────────────────────────────────────


@router.post("/settings", response_model=ReserveSettingsResponse)
async def update_settings_endpoint(
    incoming: ReserveSettings, _: AdminAccessDep, session: SessionDep
) -> ReserveSettingsResponse:
    settings = get_settings()
    saved = save_reserve_settings(_user_id(), incoming, settings=settings)
    # D22: turning "Riserva attiva" off while assets are still inside = freeze.
    service = await build_reserve_service(session, settings)
    holdings = await ReserveRepository(session).list_holdings(_user_id())
    has_assets = any(Decimal(str(h.quantity)) > 0 for h in holdings)
    await service.set_frozen(_user_id(), (not saved.settings.enabled) and has_assets)
    return saved


@router.post("/transfer", response_model=ReserveView)
async def transfer(req: TransferRequest, _: AdminAccessDep, session: SessionDep) -> ReserveView:
    try:
        amount = Decimal(str(req.amount_usd))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="amount_not_a_number")
    service = await build_reserve_service(session, get_settings())
    try:
        if req.direction == "in":
            return await service.transfer_in(_user_id(), amount)
        return await service.transfer_out(_user_id(), amount)
    except ReserveError as exc:
        raise _domain_error(exc)
    except ReserveExecutionError:
        raise HTTPException(status_code=503, detail="price_unavailable")


@router.post("/target-weights", response_model=ReserveView)
async def set_target_weights(
    req: TargetWeightsRequest, _: AdminAccessDep, session: SessionDep
) -> ReserveView:
    service = await build_reserve_service(session, get_settings())
    try:
        return await service.set_target_weights(_user_id(), req.weights)
    except (ReserveError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=getattr(exc, "code", "invalid_weights"))


@router.post("/rebalance")
async def rebalance(req: RebalanceRequest, _: AdminAccessDep, session: SessionDep) -> dict:
    service = await build_reserve_service(session, get_settings())
    try:
        return await service.rebalance(_user_id(), dry_run=req.dry_run)
    except ReserveError as exc:
        raise _domain_error(exc)
    except ReserveExecutionError:
        raise HTTPException(status_code=503, detail="price_unavailable")


@router.post("/deploy", response_model=ReserveView)
async def deploy_now(_: AdminAccessDep, session: SessionDep) -> ReserveView:
    service = await build_reserve_service(session, get_settings())
    try:
        await service.deploy(_user_id(), force=True, reason="manual")
        return await service.get_view(_user_id())
    except ReserveExecutionError:
        raise HTTPException(status_code=503, detail="price_unavailable")

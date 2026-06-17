"""Dashboard data views: Spot / Perp / Global."""

from fastapi import APIRouter

from backend.app.api.dependencies import ReadAccessDep, SessionDep, SettingsDep
from backend.app.persistence.views import ViewService
from backend.app.schemas.views import GlobalView, PerpView, SpotView

router = APIRouter(prefix="/api/v1/views", tags=["views"])


@router.get("/spot")
async def spot_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> SpotView:
    """Open spot positions, history, PnL and win rate."""

    service = ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct)
    return await service.spot_view(str(settings.default_user_id))


@router.get("/perp")
async def perp_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> PerpView:
    """Open perpetual positions (leverage, liquidation, funding), history, PnL, win rate."""

    service = ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct)
    return await service.perp_view(str(settings.default_user_id))


@router.get("/global")
async def global_view(
    session: SessionDep,
    settings: SettingsDep,
    _: ReadAccessDep,
) -> GlobalView:
    """Total PnL, capital vs initial, drawdown vs cap, exposure, balance."""

    service = ViewService(session, drawdown_cap_pct=settings.risk_max_drawdown_pct)
    return await service.global_view(str(settings.default_user_id))

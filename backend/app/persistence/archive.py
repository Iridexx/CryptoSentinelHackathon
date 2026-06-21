"""Archive dry-run data before resetting live analytics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.archives import ArchivedRun
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot, PortfolioState
from backend.app.persistence.models.trades import PerpTrade, SpotTrade


DEFAULT_ARCHIVE_LABEL = "pre_500_reset_2026_06_20"


async def archive_dry_run_records(
    session: AsyncSession,
    *,
    user_id: str,
    archive_label: str = DEFAULT_ARCHIVE_LABEL,
    delete_live: bool = True,
    reset_portfolio_capital_usd: Decimal | None = None,
) -> ArchivedRun:
    """Copy current simulated records into one archive row and remove them from live tables."""

    archived_at = datetime.now(UTC)
    spot_trades = await _scalars(session, _spot_dry_run_select(user_id))
    perp_trades = await _scalars(session, _perp_dry_run_select(user_id))
    decisions = await _scalars(session, _decision_dry_run_select(user_id))
    snapshots = await _scalars(session, select(PnlSnapshot).where(PnlSnapshot.user_id == user_id))
    portfolio = (
        await session.execute(select(PortfolioState).where(PortfolioState.user_id == user_id))
    ).scalar_one_or_none()
    payload = {
        "spot_trades": [_model_payload(row) for row in spot_trades],
        "perp_trades": [_model_payload(row) for row in perp_trades],
        "agent_decisions": [_model_payload(row) for row in decisions],
        "pnl_snapshots": [_model_payload(row) for row in snapshots],
        "portfolio_state": [_model_payload(portfolio)] if portfolio is not None else [],
    }
    archive = ArchivedRun(
        run_id=f"arch_{archived_at.strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:10]}",
        user_id=user_id,
        archive_label=archive_label,
        archived_at=archived_at,
        is_simulated=True,
        payload_json=json.dumps(payload, default=_json_default, separators=(",", ":")),
    )
    session.add(archive)

    if delete_live:
        await session.execute(delete(SpotTrade).where(SpotTrade.id.in_([row.id for row in spot_trades])))
        await session.execute(delete(PerpTrade).where(PerpTrade.id.in_([row.id for row in perp_trades])))
        await session.execute(delete(AgentDecision).where(AgentDecision.id.in_([row.id for row in decisions])))
        await session.execute(delete(PnlSnapshot).where(PnlSnapshot.id.in_([row.id for row in snapshots])))
        if portfolio is not None and reset_portfolio_capital_usd is not None:
            portfolio.total_equity_usd = reset_portfolio_capital_usd
            portfolio.initial_equity_usd = reset_portfolio_capital_usd
            portfolio.peak_equity_usd = reset_portfolio_capital_usd
            portfolio.drawdown_pct = Decimal("0")
            portfolio.max_drawdown_pct = Decimal("0")
            portfolio.exposure_pct = Decimal("0")
            portfolio.daily_pnl_usd = Decimal("0")
            portfolio.daily_loss_limit_used_pct = Decimal("0")
            portfolio.agent_status = "idle"
            portfolio.trades_today = 0
            portfolio.updated_at = archived_at

    await session.commit()
    await session.refresh(archive)
    return archive


async def list_archived_runs(session: AsyncSession, *, user_id: str) -> list[dict]:
    result = await session.execute(
        select(ArchivedRun)
        .where(ArchivedRun.user_id == user_id)
        .order_by(ArchivedRun.archived_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "run_id": row.run_id,
            "archive_label": row.archive_label,
            "archived_at": row.archived_at.isoformat(),
            "is_simulated": row.is_simulated,
            "counts": _archive_counts(row.payload_json),
        }
        for row in rows
    ]


async def _scalars(session: AsyncSession, statement) -> list:
    result = await session.execute(statement)
    return list(result.scalars().all())


def _spot_dry_run_select(user_id: str):
    return select(SpotTrade).where(SpotTrade.user_id == user_id).where(
        or_(
            SpotTrade.trade_id.like("dry_%"),
            SpotTrade.provider == "dry_run",
            SpotTrade.notes.like("%dry_run%"),
        )
    )


def _perp_dry_run_select(user_id: str):
    return select(PerpTrade).where(PerpTrade.user_id == user_id).where(
        or_(
            PerpTrade.trade_id.like("dry_%"),
            PerpTrade.venue == "dry_run",
            PerpTrade.notes.like("%dry_run%"),
        )
    )


def _decision_dry_run_select(user_id: str):
    return select(AgentDecision).where(AgentDecision.user_id == user_id).where(
        or_(
            AgentDecision.trade_id.like("dry_%"),
            AgentDecision.reasoning.like("%dry_run%"),
        )
    )


def _model_payload(row) -> dict:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _archive_counts(payload_json: str) -> dict[str, int]:
    try:
        payload = json.loads(payload_json)
    except ValueError:
        return {}
    return {key: len(value) for key, value in payload.items() if isinstance(value, list)}

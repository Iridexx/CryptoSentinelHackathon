"""R4 — reserve wired into GlobalView (D25) and the risk manager."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.agent.risk.manager import RiskManager, SignalIntent
from backend.app.core.config import Settings, load_yaml_settings
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.pnl import PortfolioState
from backend.app.persistence.models.reserve import ReserveSnapshot
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.reserve import ReserveRepository
from backend.app.persistence.views import ViewService

USER = "00000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(**load_yaml_settings())


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield
    await close_db()


async def _seed_reserve(session, *, cash="0", transferred="40", snapshot_value=None) -> None:
    repo = ReserveRepository(session)
    await repo.upsert_holding(USER, "BTC", quantity=Decimal("0.0005"), avg_cost_usd=Decimal("60000"), now=NOW)
    await repo.set_reserve_fields(
        USER, now=NOW,
        reserve_cash_usd=Decimal(cash), reserve_transferred_net_usd=Decimal(transferred),
    )
    await repo.commit()
    if snapshot_value is not None:
        await repo.save_snapshot(
            ReserveSnapshot(
                user_id=USER, timestamp_utc=NOW, total_value_usd=Decimal(snapshot_value),
                cash_usd=Decimal(cash), cost_basis_usd=Decimal(transferred),
                pnl_usd=Decimal(snapshot_value) - Decimal(transferred),
            )
        )


# ── GlobalView ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_global_view_carves_reserve_out_of_tradable_equity(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session, transferred="40", snapshot_value="41")

        view = await ViewService(session).global_view(USER)

    # total_equity = initial 500 + realized 0 + unrealized 0 = 500 (recomputed).
    assert view.tradable_equity_usd == Decimal("460")  # 500 - 40
    assert view.reserve_cost_basis_usd == Decimal("40")
    assert view.reserve_value_usd == Decimal("41")     # from snapshot
    assert view.reserve_pnl_usd == Decimal("1")
    assert view.total_portfolio_equity_usd == Decimal("501")  # 460 + 41
    # trading P&L unchanged (0), combined P&L = (501 - 500) / 500.
    assert view.pnl_total_pct == 0.0
    assert view.total_portfolio_pnl_pct == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_global_view_reserve_value_falls_back_to_cost_without_snapshot(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session, cash="10", transferred="40")  # no snapshot

        view = await ViewService(session).global_view(USER)

    # cash 10 + BTC 0.0005 * avg 60000 = 30  → 40, equal to cost basis → pnl 0.
    assert view.reserve_value_usd == Decimal("40")
    assert view.reserve_pnl_usd == Decimal("0")


@pytest.mark.asyncio
async def test_global_view_market_move_does_not_touch_tradable_equity(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        await _seed_reserve(session, transferred="40", snapshot_value="40")
        v1 = await ViewService(session).global_view(USER)

        # BTC pumps → a fresh snapshot at a higher value.
        await ReserveRepository(session).save_snapshot(
            ReserveSnapshot(
                user_id=USER, timestamp_utc=datetime(2026, 8, 30, 13, tzinfo=UTC),
                total_value_usd=Decimal("80"), cost_basis_usd=Decimal("40"),
                pnl_usd=Decimal("40"),
            )
        )
        v2 = await ViewService(session).global_view(USER)

    assert v2.tradable_equity_usd == v1.tradable_equity_usd   # unchanged
    assert v2.reserve_value_usd == Decimal("80")
    assert v2.reserve_pnl_usd == Decimal("40")
    assert v2.total_portfolio_equity_usd > v1.total_portfolio_equity_usd
    assert v2.pnl_total_pct == v1.pnl_total_pct               # trading P&L untouched


@pytest.mark.asyncio
async def test_reserve_fees_folded_into_total_fees(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("600"), initial_equity_usd=Decimal("500")
        )
        from backend.app.persistence.models.reserve import ReserveTransaction

        repo = ReserveRepository(session)
        await repo.add_transaction(
            ReserveTransaction(
                user_id=USER, type="deploy_buy", asset="BTC", value_usd=Decimal("16"),
                fee_usd=Decimal("0.17"), cash_usd_delta=Decimal("-16.17"), created_at=NOW,
            )
        )
        await repo.commit()

        view = await ViewService(session).global_view(USER)

    assert view.reserve_fees_usd == Decimal("0.17000000")
    assert view.total_fees_usd == Decimal("0.17000000")


@pytest.mark.asyncio
async def test_risk_guardrail_floor_uses_tradable_equity(db) -> None:
    async with get_session_factory()() as session:
        # total 210, but 206 is in the reserve → tradable 4 ≤ $5 floor.
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("210"), initial_equity_usd=Decimal("210")
        )
        await ReserveRepository(session).set_reserve_fields(
            USER, now=NOW, reserve_transferred_net_usd=Decimal("206"),
        )
        await ReserveRepository(session).commit()

        view = await ViewService(session).global_view(USER)

    assert view.risk_guardrail is not None
    assert view.risk_guardrail.blocked is True
    assert view.risk_guardrail.reason == "portfolio_floor_guard"


# ── risk manager sizing ─────────────────────────────────────────────────────


def _portfolio(**kw) -> PortfolioState:
    base = dict(
        user_id=USER, total_equity_usd=Decimal("1000"), initial_equity_usd=Decimal("1000"),
        peak_equity_usd=Decimal("1000"), drawdown_pct=Decimal("0"), max_drawdown_pct=Decimal("0"),
        exposure_pct=Decimal("0"), daily_pnl_usd=Decimal("0"),
        daily_loss_limit_used_pct=Decimal("0"), agent_status="idle", trades_today=0,
        updated_at=NOW,
    )
    base.update(kw)
    return PortfolioState(**base)


def _intent(**kw) -> SignalIntent:
    base = dict(
        asset="ETH", market="spot", side="long", price=Decimal("100"),
        stop_loss=Decimal("98"), quality=Decimal("0.8"), quote_equity=Decimal("1000"),
    )
    base.update(kw)
    return SignalIntent(**base)


def test_risk_manager_sizes_on_tradable_equity() -> None:
    mgr = RiskManager(_settings())
    cap = Decimal(str(_settings().risk_capital_per_trade_pct))

    no_reserve = mgr.evaluate(
        _intent(), portfolio=_portfolio(), open_spot_positions=[], open_perp_positions=[]
    )
    with_reserve = mgr.evaluate(
        _intent(), portfolio=_portfolio(reserve_transferred_net_usd=Decimal("200")),
        open_spot_positions=[], open_perp_positions=[],
    )

    assert no_reserve.size_quote == Decimal("1000") * cap / Decimal("100")
    assert with_reserve.size_quote == Decimal("800") * cap / Decimal("100")
    assert with_reserve.size_quote < no_reserve.size_quote


def test_risk_manager_floor_guard_on_tradable_equity() -> None:
    mgr = RiskManager(_settings())
    blocked = mgr.evaluate(
        _intent(), portfolio=_portfolio(total_equity_usd=Decimal("210"),
                                        reserve_transferred_net_usd=Decimal("206")),
        open_spot_positions=[], open_perp_positions=[],
    )
    ok = mgr.evaluate(
        _intent(), portfolio=_portfolio(total_equity_usd=Decimal("210")),
        open_spot_positions=[], open_perp_positions=[],
    )
    assert blocked.allowed is False and blocked.reason == "portfolio_floor_guard"
    assert ok.allowed is True


def test_risk_manager_unchanged_without_a_reserve() -> None:
    mgr = RiskManager(_settings())
    cap = Decimal(str(_settings().risk_capital_per_trade_pct))
    decision = mgr.evaluate(
        _intent(), portfolio=_portfolio(), open_spot_positions=[], open_perp_positions=[]
    )
    assert decision.allowed is True
    assert decision.size_quote == Decimal("1000") * cap / Decimal("100")

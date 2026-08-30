"""R3 — ReserveService: transfer/sweep/deploy/rebalance, §7bis, D25/D29/D30."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.core.config import Settings, load_yaml_settings
from backend.app.domain.reserve.executor import ReserveExecutionError, ReserveExecutor
from backend.app.domain.reserve.service import ReserveError, ReserveService
from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.trades import SpotTrade
from backend.app.persistence.repositories.pnl import PnlRepository

USER = "00000000-0000-0000-0000-000000000001"

PRICES = {
    "BTC": Decimal("60000"),
    "ETH": Decimal("3000"),
    "BNB": Decimal("600"),
    "SOL": Decimal("150"),
    "TRX": Decimal("0.30"),
}


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    yield
    await close_db()


def _settings() -> Settings:
    return Settings(**load_yaml_settings())


def _make_service(session, *, prices=None, clock=None, live=False) -> ReserveService:
    table = dict(PRICES if prices is None else prices)

    async def price_source(asset: str):
        return table.get(asset)

    ex = ReserveExecutor(_settings(), price_source=price_source, live=live)
    now_fn = clock or (lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC))
    return ReserveService(session, executor=ex, settings=_settings(), now_fn=now_fn)


async def _seed(session, *, initial="500", realized_profit="0") -> None:
    await PnlRepository(session).upsert_portfolio(
        USER, total_equity_usd=Decimal(initial), initial_equity_usd=Decimal(initial)
    )
    if Decimal(realized_profit) != 0:
        session.add(
            SpotTrade(
                trade_id=f"t-{realized_profit}", user_id=USER, asset="DOGE", side="sell",
                amount=Decimal("1"), price=Decimal("1"), amount_quote=Decimal("1"),
                status="closed", timestamp_utc=datetime(2026, 8, 29, tzinfo=UTC),
                pnl_usd=Decimal(realized_profit),
            )
        )
        await session.commit()


# ── §7bis: only profits ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transfer_in_rejected_without_profit(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="0")
        svc = _make_service(session)
        with pytest.raises(ReserveError) as exc:
            await svc.transfer_in(USER, Decimal("50"))
        assert exc.value.code == "no_profit_available"


@pytest.mark.asyncio
async def test_transfer_in_capped_at_profit_above_initial(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="30")
        svc = _make_service(session)
        # Ask for $50 but only $30 of profit exists.
        view = await svc.transfer_in(USER, Decimal("50"))
        fields = await svc._repo.get_reserve_fields(USER)
        assert fields["reserve_transferred_net_usd"] == Decimal("30.00000000")
        assert view.cost_basis_usd == Decimal("30.00000000")
        # $30 went to cash, then deploy spent most of it.
        assert view.value_usd < Decimal("30")  # fees
        assert view.value_usd > Decimal("29")


@pytest.mark.asyncio
async def test_transfer_in_blocked_when_frozen(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="100")
        svc = _make_service(session)
        await svc.set_frozen(USER, True)
        with pytest.raises(ReserveError) as exc:
            await svc.transfer_in(USER, Decimal("40"))
        assert exc.value.code == "frozen"


# ── sweep (§8bis) ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sweep_moves_pct_of_new_realized_profit_to_cash(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="100")
        svc = _make_service(session)
        swept = await svc.run_profit_sweep(USER)
        assert swept == Decimal("20")  # 20% of 100
        fields = await svc._repo.get_reserve_fields(USER)
        assert fields["reserve_transferred_net_usd"] == Decimal("20.00000000")
        assert fields["last_swept_realized_pnl_usd"] == Decimal("100.00000000")


@pytest.mark.asyncio
async def test_sweep_is_idempotent_without_new_profit(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="100")
        svc = _make_service(session)
        assert await svc.run_profit_sweep(USER) == Decimal("20")
        assert await svc.run_profit_sweep(USER) == Decimal("0")


@pytest.mark.asyncio
async def test_sweep_skipped_when_disabled(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="100")
        s = _settings()
        s.reserve.sweep_enabled = False
        svc = ReserveService(
            session,
            executor=ReserveExecutor(s, price_source=lambda a: _aprice(a)),
            settings=s,
            now_fn=lambda: datetime(2026, 8, 30, 12, tzinfo=UTC),
        )
        assert await svc.run_profit_sweep(USER) == Decimal("0")


async def _aprice(asset):
    return PRICES.get(asset)


# ── deploy (§8ter) ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deploy_buys_top_gaps_and_defers_small_tails(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        # sweep 20% of 1000 = 200 (capped by capacity 1000) → cash 200,
        # but we want the $40-ish case: do a manual transfer of exactly 40.
        await svc._ensure_portfolio(USER)
        # Force cash = 40 directly for a clean assertion.
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC),
            reserve_cash_usd=Decimal("40"), reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()

        res = await svc.deploy(USER, force=True)
        assert not res.skipped
        assert set(res.bought) == {"BTC", "ETH", "BNB"}
        assert res.bought["BTC"] == Decimal("16")
        assert Decimal("3.9") <= res.cash_left <= Decimal("4.1")

        holdings = {h.asset for h in await svc._repo.list_holdings(USER)}
        assert holdings == {"BTC", "ETH", "BNB"}


@pytest.mark.asyncio
async def test_deploy_prioritises_underweight_tails_once_big_three_at_target(db) -> None:
    """BTC/ETH/BNB at target, base >= $100 → SOL/TRX are the top gap_rel and get bought."""
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        await svc._ensure_portfolio(USER)
        now = datetime(2026, 8, 30, tzinfo=UTC)
        # Big three sitting exactly on target for a $100 base.
        await svc._repo.upsert_holding(USER, "BTC", quantity=Decimal("40") / PRICES["BTC"], avg_cost_usd=PRICES["BTC"], now=now)
        await svc._repo.upsert_holding(USER, "ETH", quantity=Decimal("30") / PRICES["ETH"], avg_cost_usd=PRICES["ETH"], now=now)
        await svc._repo.upsert_holding(USER, "BNB", quantity=Decimal("20") / PRICES["BNB"], avg_cost_usd=PRICES["BNB"], now=now)
        await svc._repo.set_reserve_fields(
            USER, now=now, reserve_cash_usd=Decimal("10"), reserve_transferred_net_usd=Decimal("100"),
        )
        await svc._repo.commit()

        res = await svc.deploy(USER, force=True)
        assert set(res.bought) == {"SOL", "TRX"}
        assert res.bought["SOL"] == pytest.approx(Decimal("5"), abs=Decimal("0.01"))


@pytest.mark.asyncio
async def test_deploy_skips_without_trigger(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        await svc._ensure_portfolio(USER)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("10"),
            last_deploy_at=datetime(2026, 8, 30, 11, tzinfo=UTC),
        )
        await svc._repo.commit()
        res = await svc.deploy(USER)  # cash 10 < 40, deployed 1h ago
        assert res.skipped and res.reason == "no_trigger"


# ── transfer out ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transfer_out_drains_cash_then_sells_and_credits_net(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        await svc._ensure_portfolio(USER)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
            reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()
        await svc.deploy(USER, force=True)  # cash ~4, assets ~36

        before = await svc._repo.get_reserve_fields(USER)
        view = await svc.transfer_out(USER, Decimal("20"))
        after = await svc._repo.get_reserve_fields(USER)

        # transferred_net drops by what the trading book actually received (net of fees).
        assert after["reserve_transferred_net_usd"] < before["reserve_transferred_net_usd"]
        assert after["reserve_transferred_net_usd"] >= Decimal("19")  # 40 - ~20
        assert view.value_usd < Decimal("21")


@pytest.mark.asyncio
async def test_transfer_out_cooldown(db) -> None:
    times = iter([
        datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        datetime(2026, 8, 30, 12, 0, tzinfo=UTC),  # get_view after first
        datetime(2026, 8, 30, 13, 0, tzinfo=UTC),  # second, 1h later < 24h
    ])
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session, clock=lambda: next(times))
        await svc._ensure_portfolio(USER)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
            reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()
        await svc.transfer_out(USER, Decimal("5"))
        with pytest.raises(ReserveError) as exc:
            await svc.transfer_out(USER, Decimal("5"))
        assert exc.value.code == "cooldown"


@pytest.mark.asyncio
async def test_transfer_out_blocked_during_drawdown_guard(db) -> None:
    async with get_session_factory()() as session:
        await PnlRepository(session).upsert_portfolio(
            USER, total_equity_usd=Decimal("400"), initial_equity_usd=Decimal("500"),
            drawdown_pct=Decimal("20"),  # >= 15 cap
        )
        svc = _make_service(session)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
            reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()
        with pytest.raises(ReserveError) as exc:
            await svc.transfer_out(USER, Decimal("10"))
        assert exc.value.code == "drawdown_guard"


# ── D25: tradable equity does not move with the market ───────────────────────


@pytest.mark.asyncio
async def test_market_move_changes_pnl_not_tradable_equity(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        await svc._ensure_portfolio(USER)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
            reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()
        await svc.deploy(USER, force=True)

        v1 = await svc.get_view(USER)

        # BTC doubles.
        hot = dict(PRICES, BTC=Decimal("120000"))
        svc2 = _make_service(session, prices=hot)
        v2 = await svc2.get_view(USER)

        assert v2.tradable_equity_usd == v1.tradable_equity_usd  # unchanged
        assert v2.value_usd > v1.value_usd
        assert v2.pnl_usd > v1.pnl_usd


# ── D30: fees ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fees_tracked_and_drag_pnl(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        await svc._ensure_portfolio(USER)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
            reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()
        await svc.deploy(USER, force=True)

        view = await svc.get_view(USER)
        assert view.fees_total_usd > Decimal("0")
        # value = 40 - fees  (nothing moved in/out, only internal buys)
        assert view.value_usd == pytest.approx(Decimal("40") - view.fees_total_usd, abs=Decimal("0.01"))
        assert view.pnl_usd < 0  # the fee drag


# ── atomicity ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deploy_rolls_back_fully_when_a_leg_fails(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        # ETH has no price → executor raises mid-deploy.
        svc = _make_service(session, prices={"BTC": Decimal("60000"), "BNB": Decimal("600")})
        await svc._ensure_portfolio(USER)
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
            reserve_transferred_net_usd=Decimal("40"),
        )
        await svc._repo.commit()

        with pytest.raises(ReserveExecutionError):
            await svc.deploy(USER, force=True)

    async with get_session_factory()() as session:
        svc = _make_service(session)
        assert await svc._repo.list_holdings(USER) == []
        fields = await svc._repo.get_reserve_fields(USER)
        assert fields["reserve_cash_usd"] == Decimal("40.00000000")  # untouched
        assert await svc._repo.list_transactions(USER) == []


# ── frozen + weights ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_frozen_blocks_deploy_and_sweep(db) -> None:
    async with get_session_factory()() as session:
        await _seed(session, initial="500", realized_profit="1000")
        svc = _make_service(session)
        await svc.set_frozen(USER, True)
        assert await svc.run_profit_sweep(USER) == Decimal("0")
        await svc._repo.set_reserve_fields(
            USER, now=datetime(2026, 8, 30, tzinfo=UTC), reserve_cash_usd=Decimal("40"),
        )
        await svc._repo.commit()
        res = await svc.deploy(USER, force=True)
        assert res.skipped and res.reason == "frozen"

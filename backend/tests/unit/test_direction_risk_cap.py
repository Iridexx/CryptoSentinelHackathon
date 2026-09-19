"""Tetto di rischio direzionale (perp).

Scenario di riferimento: il 30/08/2026 notte quattro long su alt (TRX, DOGE, ADA, LTC)
aperti nell'arco di un'ora con BTC ribassista, tutti stoppati in mezz'ora. Il risk
manager contava solo posizioni e margine, non la direzione: 4 long correlati sono una
sola scommessa con size x4.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.agent.risk import RiskDecision, RiskManager, SignalIntent
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.pnl import PortfolioState
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.models.trades import PerpTrade
from backend.app.persistence.repositories.trades import PerpTradeRepository
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.tests.unit.test_agent_step6 import USER_ID, settings

EQUITY = Decimal("1000")


def _ms(**overrides) -> AgentMobileSettings:
    payload = dict(
        perp_fixed_margin_enabled=True,
        perp_fixed_margin_usd=50,
        perp_max_exposure_pct=100,
        perp_max_open_positions=10,
        perp_direction_risk_cap_enabled=True,
        perp_direction_risk_cap_mode="solo_in_perdita",
        perp_direction_risk_cap_loss_pct=0.5,
        perp_direction_risk_cap_pct=6.0,
        perp_direction_risk_cap_safety_mult=1.3,
    )
    payload.update(overrides)
    return AgentMobileSettings(**payload)


def _portfolio() -> PortfolioState:
    return PortfolioState(
        user_id=str(USER_ID),
        total_equity_usd=EQUITY,
        initial_equity_usd=EQUITY,
        peak_equity_usd=EQUITY,
        drawdown_pct=Decimal("0"),
        max_drawdown_pct=Decimal("0"),
        exposure_pct=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        daily_loss_limit_used_pct=Decimal("0"),
        agent_status="idle",
        trades_today=0,
        updated_at=datetime.now(UTC),
    )


def _intent(**overrides) -> SignalIntent:
    payload = dict(
        asset="TOKEN_1",
        market="perp",
        side="long",
        price=Decimal("100"),
        stop_loss=Decimal("98"),
        quality=Decimal("0.8"),
        quote_equity=EQUITY,
        leverage=28,
    )
    payload.update(overrides)
    return SignalIntent(**payload)


def _position(
    index: int,
    *,
    side: str = "long",
    entry: str = "100",
    current: str = "100",
    size: str = "14",
    stop: str | None = "98",
    trailing: str | None = None,
    pnl_unrealized: str = "0",
) -> PerpPosition:
    now = datetime.now(UTC)
    return PerpPosition(
        position_id=f"pos-{index}",
        user_id=str(USER_ID),
        asset=f"ASSET{index}",
        side=side,
        size=Decimal(size),
        entry_price=Decimal(entry),
        current_price=Decimal(current),
        leverage=28,
        pnl_unrealized=Decimal(pnl_unrealized),
        stop_loss=Decimal(stop) if stop is not None else None,
        trailing_stop=Decimal(trailing) if trailing is not None else None,
        opened_at=now,
        updated_at=now,
    )


def _evaluate(intent, positions, ms, **kwargs) -> RiskDecision:
    return RiskManager(settings()).evaluate(
        intent,
        portfolio=_portfolio(),
        open_spot_positions=[],
        open_perp_positions=positions,
        ms=ms,
        **kwargs,
    )


# ---------------------------------------------------------------- solo_in_perdita


def test_solo_in_perdita_lets_first_entry_through() -> None:
    assert _evaluate(_intent(), [], _ms()).allowed is True


def test_solo_in_perdita_blocks_when_same_side_positions_are_losing() -> None:
    # 10 unita a -1 = -10$ = -1% dell'equity: oltre la soglia dello 0,5%.
    losing = _position(1, current="99", size="10")
    decision = _evaluate(_intent(), [losing], _ms())
    assert decision.allowed is False
    assert decision.reason == "direction_risk_cap_guard"


def test_solo_in_perdita_does_not_cut_entries_while_in_profit() -> None:
    winning = _position(1, current="103", size="10")
    assert _evaluate(_intent(), [winning], _ms()).allowed is True


def test_solo_in_perdita_tolerates_small_loss_under_threshold() -> None:
    # -3$ = -0,3% dell'equity, sotto lo 0,5%: passa (era il caso di DOGE il 30/8).
    slightly_down = _position(1, current="99.7", size="10")
    assert _evaluate(_intent(), [slightly_down], _ms()).allowed is True


def test_solo_in_perdita_nets_winners_against_losers() -> None:
    losing = _position(1, current="99", size="10")  # -10$
    winning = _position(2, current="102", size="10")  # +20$
    assert _evaluate(_intent(), [losing, winning], _ms()).allowed is True


def test_solo_in_perdita_ignores_fees_in_pnl_unrealized() -> None:
    # pnl_unrealized e' al netto della fee di apertura: quattro posizioni appena aperte a
    # prezzo invariato non devono scattare per le sole fee.
    fresh = [_position(i, current="100", pnl_unrealized="-5") for i in range(4)]
    assert _evaluate(_intent(), fresh, _ms()).allowed is True


def test_solo_in_perdita_ignores_opposite_direction() -> None:
    losing_shorts = [_position(1, side="short", current="105", size="10")]
    assert _evaluate(_intent(side="long"), losing_shorts, _ms()).allowed is True
    losing_long = [_position(2, side="long", current="95", size="10")]
    assert _evaluate(_intent(side="short"), losing_long, _ms()).allowed is True


def test_direction_risk_cap_disabled_lets_everything_through() -> None:
    losing = _position(1, current="99", size="10")
    ms = _ms(perp_direction_risk_cap_enabled=False)
    assert _evaluate(_intent(), [losing], ms).allowed is True


def test_direction_risk_cap_does_not_apply_to_spot() -> None:
    losing = _position(1, current="99", size="10")
    decision = _evaluate(_intent(market="spot"), [losing], _ms())
    assert decision.reason != "direction_risk_cap_guard"


def test_recent_stops_block_even_with_nothing_open() -> None:
    ms = _ms(perp_direction_risk_cap_recent_stops_minutes=60)
    # Stop chiuso da poco: -8$ = -0,8% dell'equity, sopra la soglia.
    blocked = _evaluate(_intent(), [], ms, recent_same_direction_loss_usd=Decimal("8"))
    assert blocked.allowed is False
    assert blocked.reason == "direction_risk_cap_guard"
    # Sotto la soglia o senza stop recenti passa.
    assert _evaluate(_intent(), [], ms, recent_same_direction_loss_usd=Decimal("3")).allowed is True
    assert _evaluate(_intent(), [], ms).allowed is True


def test_recent_stops_add_to_open_pnl() -> None:
    # -3$ aperti e -3$ da uno stop recente: -0,6% insieme, oltre lo 0,5%.
    slightly_down = _position(1, current="99.7", size="10")
    decision = _evaluate(_intent(), [slightly_down], _ms(), recent_same_direction_loss_usd=Decimal("3"))
    assert decision.allowed is False


# ---------------------------------------------------------------- sempre


def _sempre(**overrides) -> AgentMobileSettings:
    return _ms(perp_direction_risk_cap_mode="sempre", **overrides)


def test_sempre_allows_entry_within_cap() -> None:
    # Nuovo: 50$ x 28 x 2% = 28$; x1,3 = 36,4$ = 3,6% dell'equity, sotto il 6%.
    assert _evaluate(_intent(), [], _sempre()).allowed is True


def test_sempre_blocks_second_entry_that_pushes_risk_over_cap() -> None:
    # Aperta: 14 x (100-98) = 28$. Con la nuova (28$) fa 56$ x1,3 = 72,8$ = 7,3% > 6%.
    decision = _evaluate(_intent(), [_position(1)], _sempre())
    assert decision.allowed is False
    assert decision.reason == "direction_risk_cap_guard"


def test_sempre_counts_breakeven_stop_as_zero_risk() -> None:
    # Stop sopra l'entrata (breakeven o profitto): la posizione non puo' piu' far perdere.
    protected = _position(1, current="103", stop="101")
    assert _evaluate(_intent(), [protected], _sempre()).allowed is True


def test_sempre_uses_trailing_stop_when_tighter() -> None:
    # stop_loss a 98 rischierebbe 28$, ma il trailing a 100,5 e' sopra l'entrata: rischio 0.
    trailed = _position(1, current="103", stop="98", trailing="100.5")
    assert _evaluate(_intent(), [trailed], _sempre()).allowed is True


def test_sempre_counts_missing_stop_as_full_margin() -> None:
    # Senza stop il rischio e' il margine intero: 100*14/28 = 50$. Con la nuova 78$ x1,3 = 10%.
    no_stop = _position(1, stop=None)
    assert _evaluate(_intent(), [no_stop], _sempre()).allowed is False


def test_sempre_blocks_single_signal_whose_own_risk_exceeds_cap() -> None:
    # Stop al 4%: 50 x 28 x 4% = 56$ x1,3 = 72,8$ = 7,3% dell'equity, da solo oltre il 6%.
    wide = _intent(stop_loss=Decimal("96"))
    assert _evaluate(wide, [], _sempre()).allowed is False


def test_sempre_safety_multiplier_is_configurable() -> None:
    # Senza margine di sicurezza: 56$ = 5,6% <= 6%, passa.
    ms = _sempre(perp_direction_risk_cap_safety_mult=1.0)
    assert _evaluate(_intent(), [_position(1)], ms).allowed is True


def test_sempre_ignores_opposite_direction() -> None:
    shorts = [_position(i, side="short", entry="100", current="100", stop="102") for i in range(3)]
    assert _evaluate(_intent(side="long"), shorts, _sempre()).allowed is True


# ---------------------------------------------------------------- impostazioni


def test_direction_risk_cap_defaults_are_on_and_least_invasive() -> None:
    ms = AgentMobileSettings()
    assert ms.perp_direction_risk_cap_enabled is True
    assert ms.perp_direction_risk_cap_mode == "solo_in_perdita"
    assert ms.perp_direction_risk_cap_loss_pct == 0.5
    assert ms.perp_direction_risk_cap_pct == 6.0
    assert ms.perp_direction_risk_cap_safety_mult == 1.3
    assert ms.perp_direction_risk_cap_recent_stops_minutes == 0


def test_direction_risk_cap_mode_rejects_unknown_value() -> None:
    with pytest.raises(ValidationError):
        AgentMobileSettings(perp_direction_risk_cap_mode="boh")


# ---------------------------------------------------------------- repository stop recenti


@pytest.fixture
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'cap.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'cap.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _trade(trade_id: str, *, side: str, direction: str, pnl: str | None, minutes_ago: int) -> PerpTrade:
    return PerpTrade(
        trade_id=trade_id,
        user_id=str(USER_ID),
        asset="TRX",
        side=side,
        direction=direction,
        size=Decimal("1"),
        price=Decimal("1"),
        leverage=28,
        status="confirmed",
        timestamp_utc=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        venue="dry_run",
        pnl_usd=Decimal(pnl) if pnl is not None else None,
    )


async def test_sum_recent_losses_counts_only_same_side_losing_closes_in_window(db) -> None:
    async with get_session_factory()() as session:
        repo = PerpTradeRepository(session)
        for trade in (
            _trade("a", side="long", direction="close", pnl="-5", minutes_ago=10),
            _trade("b", side="long", direction="close", pnl="-3", minutes_ago=30),
            _trade("c", side="long", direction="close", pnl="4", minutes_ago=20),  # vincita: non conta
            _trade("d", side="long", direction="close", pnl="-9", minutes_ago=120),  # fuori finestra
            _trade("e", side="short", direction="close", pnl="-7", minutes_ago=10),  # altra direzione
            _trade("f", side="long", direction="open", pnl=None, minutes_ago=5),  # apertura
        ):
            await repo.save(trade)
        since = datetime.now(UTC) - timedelta(minutes=60)
        assert await repo.sum_recent_losses(str(USER_ID), "long", since) == Decimal("8")
        assert await repo.sum_recent_losses(str(USER_ID), "short", since) == Decimal("7")
        assert await repo.sum_recent_losses(str(USER_ID), "long", datetime.now(UTC)) == Decimal("0")

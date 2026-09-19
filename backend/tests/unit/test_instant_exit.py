"""Uscita totale istantanea (perp).

Analisi sui trade dal 1/8 al 19/9: quando il prezzo raggiunge un quarto della strada tra ingresso
e stop, la posizione quasi sempre finisce peggio di cosi'. Lo Smart SL vende a pezzi e solo dopo
5 minuti di conferma a tempo (`confirmation_candles` x 300 s), al prezzo di quel momento: metà
del vantaggio si perdeva nel ritardo. L'uscita istantanea chiude tutto al primo controllo del
ciclo veloce dopo il tocco del livello e, quando e' attiva, sospende lo Smart SL.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.agent.service import AgentService, _instant_exit_level
from backend.app.execution.venues.dry_run import DRY_RUN_VENUE
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.repositories.trades import PerpTradeRepository
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.tests.unit.test_agent_step6 import settings as agent_settings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
ENTRY = Decimal("100")
SIZE = Decimal("10")
NOW = datetime(2026, 9, 19, tzinfo=UTC)
# Stop originale a 90 (long) / 110 (short): distanza 10. Al 25% il livello sta a 97,5 / 102,5.


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'instant.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'instant.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _ms(**overrides) -> AgentMobileSettings:
    base = dict(
        perp_instant_exit_enabled=True,
        perp_instant_exit_level_pct=25.0,
        perp_smart_sl_enabled=False,
        perp_trailing_enabled=False,
        perp_protection_mode="off",
        perp_time_stop_enabled=False,
        perp_breakeven_enabled=False,
        perp_fee_mode="none",
        perp_regime_derisk_enabled=False,
        perp_regime_flip_enabled=False,
        execution_mode="dry_run",
    )
    base.update(overrides)
    return AgentMobileSettings(**base)


def _position(side: str = "long", **overrides) -> PerpPosition:
    is_long = side == "long"
    fields = dict(
        position_id=f"instant_{side}",
        user_id=str(USER_ID),
        asset="ADA",
        side=side,
        size=SIZE,
        entry_price=ENTRY,
        current_price=ENTRY,
        leverage=28,
        pnl_unrealized=Decimal("0"),
        stop_loss=Decimal("90") if is_long else Decimal("110"),
        initial_stop_loss=Decimal("90") if is_long else Decimal("110"),
        take_profit_1=Decimal("110") if is_long else Decimal("90"),
        take_profit_2=Decimal("120") if is_long else Decimal("80"),
        entry_atr=Decimal("5"),
        opening_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        funding_accrued_usd=Decimal("0"),
        status="open",
        venue=DRY_RUN_VENUE,
        opened_at=NOW,
        updated_at=NOW,
    )
    fields.update(overrides)
    return PerpPosition(**fields)


async def _tick(pos: PerpPosition, price: Decimal, ms: AgentMobileSettings) -> None:
    set_runtime_value(str(USER_ID), "mobile_agent_settings", ms.model_dump_json())
    service = AgentService(agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    pos.current_price = price
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], NOW)


async def _closing_notes() -> list[str]:
    async with get_session_factory()() as session:
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))
    return [t.notes for t in trades if t.direction == "close"]


# ---------------------------------------------------------------- comportamento


@pytest.mark.asyncio
async def test_long_holds_above_the_level_and_exits_in_full_when_it_is_touched(db) -> None:
    pos = _position("long")

    await _tick(pos, Decimal("98"), _ms())
    assert pos.status == "open", "sopra il livello (97,5) non succede nulla"

    await _tick(pos, Decimal("97.4"), _ms())
    assert pos.status == "closed"
    assert pos.size == 0 or pos.status == "closed"
    assert await _closing_notes() == ["auto_close:instant_exit"]


@pytest.mark.asyncio
async def test_exit_fills_at_market_price_not_at_the_level(db) -> None:
    """Il fill e' il prezzo del tick: cosi' il dry-run mostra il costo reale del controllo a intervalli."""
    pos = _position("long")
    await _tick(pos, Decimal("96.5"), _ms())

    async with get_session_factory()() as session:
        closes = [t for t in await PerpTradeRepository(session).list_for_user(str(USER_ID)) if t.direction == "close"]
    assert len(closes) == 1
    assert closes[0].price == Decimal("96.5")
    assert closes[0].pnl_usd == (Decimal("96.5") - ENTRY) * SIZE


@pytest.mark.asyncio
async def test_short_is_mirrored(db) -> None:
    pos = _position("short")

    await _tick(pos, Decimal("102"), _ms())
    assert pos.status == "open"

    await _tick(pos, Decimal("102.6"), _ms())
    assert pos.status == "closed"
    assert await _closing_notes() == ["auto_close:instant_exit"]


@pytest.mark.asyncio
async def test_level_follows_the_configured_percentage(db) -> None:
    pos = _position("long")
    ms = _ms(perp_instant_exit_level_pct=50.0)  # livello a 95

    await _tick(pos, Decimal("96"), ms)
    assert pos.status == "open"
    await _tick(pos, Decimal("94.9"), ms)
    assert pos.status == "closed"


@pytest.mark.asyncio
async def test_disabled_by_default_does_nothing(db) -> None:
    pos = _position("long")

    await _tick(pos, Decimal("96"), _ms(perp_instant_exit_enabled=False))

    assert pos.status == "open"
    assert await _closing_notes() == []


# ---------------------------------------------------------------- Smart SL sospeso


@pytest.mark.asyncio
async def test_smart_sl_is_suspended_while_instant_exit_is_on(db) -> None:
    """Prezzo oltre L1 e L2 dello Smart SL ma prima del livello di uscita: lo Smart SL non deve toccare nulla."""
    pos = _position("long")
    ms = _ms(perp_smart_sl_enabled=True, perp_instant_exit_level_pct=90.0)  # uscita a 91; L1 96,7; L2 93,3

    await _tick(pos, Decimal("93"), ms)

    assert pos.status == "open"
    assert pos.smart_sl_state is None, "lo Smart SL non ha nemmeno inizializzato il suo stato"
    assert pos.size == SIZE


@pytest.mark.asyncio
async def test_smart_sl_still_runs_when_instant_exit_is_off(db) -> None:
    """Controllo di coerenza del test sopra: senza uscita istantanea lo stesso scenario attiva lo Smart SL."""
    pos = _position("long")
    ms = _ms(perp_instant_exit_enabled=False, perp_smart_sl_enabled=True)

    await _tick(pos, Decimal("93"), ms)

    assert pos.smart_sl_state is not None


@pytest.mark.asyncio
async def test_the_saved_smart_sl_preference_is_not_changed(db) -> None:
    """La sospensione e' a runtime: chi disattiva l'uscita istantanea ritrova lo Smart SL com'era."""
    ms = _ms(perp_smart_sl_enabled=True)
    set_runtime_value(str(USER_ID), "mobile_agent_settings", ms.model_dump_json())
    service = AgentService(agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace())
    pos = _position("long")
    pos.current_price = Decimal("93")
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], NOW)

    assert service._ms.perp_smart_sl_enabled is True, "il valore salvato dello Smart SL resta acceso"
    assert service._ms.perp_instant_exit_enabled is True
    assert pos.smart_sl_state is None, "ma non ha agito"


# ---------------------------------------------------------------- dove non si applica


@pytest.mark.asyncio
async def test_not_applied_without_an_initial_stop(db) -> None:
    pos = _position("long", initial_stop_loss=None)

    await _tick(pos, Decimal("96"), _ms())

    assert pos.status == "open"


@pytest.mark.asyncio
async def test_not_applied_once_the_stop_is_at_breakeven(db) -> None:
    """Stop gia' salito a breakeven: la posizione e' protetta, chiude lo stop e non c'e' perdita da limitare."""
    pos = _position("long", stop_loss=Decimal("100"))

    await _tick(pos, Decimal("96"), _ms())

    assert pos.status == "closed"
    assert await _closing_notes() == ["auto_close:breakeven"]


@pytest.mark.asyncio
async def test_regime_flip_positions_are_excluded(db) -> None:
    """Le posizioni flip di regime sono coperture a stop stretto con la loro uscita dedicata."""
    set_runtime_value(
        str(USER_ID),
        "btc_trend_shock",
        json.dumps({"state": "BLOCKED", "recovery_count": 0, "direction": "bearish", "score": 2, "adx": 41.0}),
    )
    pos = _position("short", smart_sl_state=json.dumps({"regime_flip_direction": "bearish"}))

    await _tick(pos, Decimal("102.6"), _ms())

    assert pos.status == "open"


# ---------------------------------------------------------------- livello e impostazioni


def test_instant_exit_level_for_long_and_short() -> None:
    assert _instant_exit_level(_position("long"), 25.0) == Decimal("97.5")
    assert _instant_exit_level(_position("short"), 25.0) == Decimal("102.5")
    assert _instant_exit_level(_position("long"), 50.0) == Decimal("95")


def test_instant_exit_level_is_none_when_it_does_not_apply() -> None:
    assert _instant_exit_level(_position("long", initial_stop_loss=None), 25.0) is None
    assert _instant_exit_level(_position("long", stop_loss=Decimal("100")), 25.0) is None
    assert _instant_exit_level(_position("short", stop_loss=Decimal("100")), 25.0) is None
    assert _instant_exit_level(_position("long", initial_stop_loss=Decimal("100")), 25.0) is None


def test_instant_exit_defaults_are_off_and_at_a_quarter() -> None:
    ms = AgentMobileSettings()
    assert ms.perp_instant_exit_enabled is False
    assert ms.perp_instant_exit_level_pct == 25.0


@pytest.mark.parametrize("value", [4.9, 90.1, 0.0, -5.0])
def test_instant_exit_level_is_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        AgentMobileSettings(perp_instant_exit_level_pct=value)

"""De-risk di regime: il filtro shock BTC agisce sulle posizioni GIA' aperte.

Scenario ricostruito dal crollo del 30/08/2026 notte: quattro long perp aperte a
leva alta mentre BTC scendeva, il guard shock che scattava solo a capitolazione
avvenuta e, soprattutto, che non toccava l'esposizione gia' in essere. Le
posizioni sono uscite intere sullo stop pieno perche':

* il trailing non poteva agganciare sotto l'entry (posizioni mai in profitto);
* nulla riduceva la size quando il regime girava contro.

Qui si congela il comportamento nuovo: chiusura parziale una-tantum, stop stretto
sul residuo, rebuy dello smart SL congelato, e nessun effetto quando il regime e'
normale o e' a favore della posizione.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.service import AgentService
from backend.app.execution.venues.dry_run import DRY_RUN_VENUE
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.models.positions import PerpPosition
from backend.app.persistence.runtime_state import set_runtime_value
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.tests.unit.test_agent_step6 import settings as agent_settings

USER_ID = UUID("00000000-0000-0000-0000-000000000001")

ENTRY = Decimal("100")
SIZE = Decimal("10")
ATR = Decimal("5")
NOW = datetime(2026, 8, 31, tzinfo=UTC)


@pytest.fixture()
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'derisk.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'derisk.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def _mobile_settings(**overrides) -> AgentMobileSettings:
    base = dict(
        perp_protection_mode="trailing",
        perp_trailing_enabled=True,
        perp_smart_sl_enabled=False,
        perp_time_stop_enabled=False,
        perp_breakeven_enabled=False,
        perp_fee_mode="none",
        perp_regime_derisk_enabled=True,
        perp_regime_derisk_fraction=50.0,
        perp_regime_flip_enabled=False,
        execution_mode="dry_run",
    )
    base.update(overrides)
    return AgentMobileSettings(**base)


def _position(side: str = "long") -> PerpPosition:
    is_long = side == "long"
    return PerpPosition(
        position_id=f"derisk_{side}",
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
        entry_atr=ATR,
        opening_fee_usd=Decimal("0"),
        slippage_usd=Decimal("0"),
        funding_accrued_usd=Decimal("0"),
        status="open",
        venue=DRY_RUN_VENUE,
        opened_at=NOW,
        updated_at=NOW,
    )


def _set_regime(state: str, direction: str | None) -> None:
    set_runtime_value(
        str(USER_ID),
        "btc_trend_shock",
        json.dumps({"state": state, "recovery_count": 0, "direction": direction, "score": 2, "adx": 41.0}),
    )


async def _tick(pos: PerpPosition, price: Decimal, ms: AgentMobileSettings) -> None:
    set_runtime_value(str(USER_ID), "mobile_agent_settings", ms.model_dump_json())
    service = AgentService(
        agent_settings(), spot_registry=SimpleNamespace(), perp_registry=SimpleNamespace()
    )
    pos.current_price = price
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [], [pos], NOW)


@pytest.mark.asyncio
async def test_long_derisked_when_btc_regime_turns_bearish(db) -> None:
    """Long + shock bearish: chiude meta' size e aggancia lo stop stretto sotto l'entry."""
    _set_regime("BLOCKED", "bearish")
    pos = _position("long")

    await _tick(pos, Decimal("99"), _mobile_settings())

    assert pos.status == "open"
    assert pos.size == SIZE / 2, "il de-risk chiude il 50% della posizione"
    assert not pos.tp1_reached, "il de-risk non e' un take-profit: non marca TP1"
    # Trailing agganciato sotto l'entry — impossibile prima di questa modifica.
    assert pos.trailing_stop is not None
    assert pos.trailing_stop < pos.entry_price
    assert pos.trailing_stop > pos.stop_loss, "deve essere piu' protettivo dello stop iniziale"
    assert pos.trailing_stop < Decimal("99"), "mai oltre il prezzo corrente: chiuderebbe subito il residuo"


@pytest.mark.asyncio
async def test_derisk_happens_once_even_if_regime_flaps(db) -> None:
    """Il regime oscilla BLOCKED/NORMAL/BLOCKED: la size non viene erosa a fette."""
    _set_regime("BLOCKED", "bearish")
    pos = _position("long")
    ms = _mobile_settings()

    await _tick(pos, Decimal("99"), ms)
    size_after_first = pos.size

    _set_regime("NORMAL", None)
    await _tick(pos, Decimal("99.5"), ms)
    _set_regime("BLOCKED", "bearish")
    await _tick(pos, Decimal("99"), ms)

    assert pos.size == size_after_first


@pytest.mark.asyncio
async def test_no_derisk_when_regime_is_normal(db) -> None:
    _set_regime("NORMAL", None)
    pos = _position("long")

    await _tick(pos, Decimal("99"), _mobile_settings())

    assert pos.size == SIZE
    assert pos.trailing_stop is None


@pytest.mark.asyncio
async def test_no_derisk_when_regime_favours_the_position(db) -> None:
    """Shock bullish e posizione long: il regime e' a favore, non si tocca nulla."""
    _set_regime("BLOCKED", "bullish")
    pos = _position("long")

    await _tick(pos, Decimal("99"), _mobile_settings())

    assert pos.size == SIZE


@pytest.mark.asyncio
async def test_short_derisked_when_regime_turns_bullish(db) -> None:
    """Lo short e' speculare: shock bullish contro uno short lo riduce."""
    _set_regime("BLOCKED", "bullish")
    pos = _position("short")

    await _tick(pos, Decimal("101"), _mobile_settings())

    assert pos.size == SIZE / 2
    assert pos.trailing_stop is not None
    assert pos.trailing_stop > pos.entry_price
    assert pos.trailing_stop < pos.stop_loss
    assert pos.trailing_stop > Decimal("101")


@pytest.mark.asyncio
async def test_require_contrarian_off_derisks_every_position(db) -> None:
    _set_regime("BLOCKED", "bullish")
    pos = _position("long")

    await _tick(pos, Decimal("99"), _mobile_settings(perp_regime_derisk_require_contrarian=False))

    assert pos.size == SIZE / 2


@pytest.mark.asyncio
async def test_disabled_flag_restores_previous_behaviour(db) -> None:
    _set_regime("BLOCKED", "bearish")
    pos = _position("long")

    await _tick(pos, Decimal("99"), _mobile_settings(perp_regime_derisk_enabled=False))

    assert pos.size == SIZE
    assert pos.trailing_stop is None, "senza de-risk il trailing resta bloccato sopra l'entry"


def _sold_l1_state(entry: Decimal, size: Decimal) -> str:
    """Stato smart-SL con il livello L1 gia' venduto, pronto per il rebuy above_entry."""
    return json.dumps(
        {
            "original_size": str(size),
            "original_entry": str(entry),
            "global_reentries": 0,
            # Conferma gia' maturata: il rebuy scatterebbe a questo tick.
            "rebuy_above_confirm_since": "2026-08-30T23:00:00+00:00",
            "levels": [
                {"status": "sold", "sell_price": "97", "reentries": 0, "confirm_since": None, "rebuy_confirm_since": None},
                {"status": "idle", "sell_price": None, "reentries": 0, "confirm_since": None, "rebuy_confirm_since": None},
            ],
        }
    )


@pytest.mark.asyncio
async def test_rebuy_frozen_while_regime_is_adverse(db) -> None:
    """In regime avverso lo smart SL non ricompra: sarebbe esposizione dentro il crollo."""
    _set_regime("BLOCKED", "bearish")
    pos = _position("long")
    pos.size = SIZE * Decimal("0.75")  # L1 (25%) gia' venduto
    pos.smart_sl_state = _sold_l1_state(ENTRY, SIZE)
    ms = _mobile_settings(
        perp_smart_sl_enabled=True,
        perp_smart_sl_rebuy_mode="above_entry",
        perp_regime_derisk_fraction=0.0,  # isola il solo effetto del freeze
    )

    # Prezzo sopra l'entry originale: senza freeze il rebuy scatterebbe.
    await _tick(pos, Decimal("101"), ms)

    assert json.loads(pos.smart_sl_state)["levels"][0]["status"] == "sold"
    assert pos.size == SIZE * Decimal("0.75"), "nessun rientro finche' il regime e' avverso"


@pytest.mark.asyncio
async def test_rebuy_allowed_again_when_regime_is_normal(db) -> None:
    """Controprova: stesso stato, regime normale -> il rebuy avviene."""
    _set_regime("NORMAL", None)
    pos = _position("long")
    pos.size = SIZE * Decimal("0.75")
    pos.smart_sl_state = _sold_l1_state(ENTRY, SIZE)
    ms = _mobile_settings(
        perp_smart_sl_enabled=True,
        perp_smart_sl_rebuy_mode="above_entry",
    )

    await _tick(pos, Decimal("101"), ms)

    assert pos.size > SIZE * Decimal("0.75")


@pytest.mark.asyncio
async def test_residual_exit_is_labelled_as_regime_stop(db) -> None:
    """L'uscita sullo stop stretto da shock non deve figurare come trailing normale."""
    from backend.app.persistence.repositories.trades import PerpTradeRepository

    _set_regime("BLOCKED", "bearish")
    pos = _position("long")
    ms = _mobile_settings()

    await _tick(pos, Decimal("99"), ms)          # de-risk 50% + trailing stretto
    trail = pos.trailing_stop
    assert trail is not None
    await _tick(pos, trail - Decimal("0.5"), ms)  # il prezzo sfonda lo stop stretto

    assert pos.status == "closed"
    async with get_session_factory()() as session:
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))
    reasons = [(t.notes or "").replace("auto_close:", "") for t in trades if t.direction == "close"]
    assert "regime_derisk_stop" in reasons
    assert "trailing_stop" not in reasons


@pytest.mark.asyncio
async def test_flip_closes_full_and_reopens_opposite_side(db) -> None:
    """Con flip attivo: chiude il 100% del long e riapre uno short, stessa leva."""
    from backend.app.persistence.repositories.positions import PerpPositionRepository

    _set_regime("BLOCKED", "bearish")
    pos = _position("long")

    await _tick(pos, Decimal("99"), _mobile_settings(perp_regime_flip_enabled=True))

    assert pos.status == "closed"
    async with get_session_factory()() as session:
        open_positions = await PerpPositionRepository(session).open_for_user(str(USER_ID))
    flips = [p for p in open_positions if p.asset == "ADA" and p.side == "short"]
    assert len(flips) == 1
    flip = flips[0]
    assert flip.leverage == pos.leverage
    assert json.loads(flip.smart_sl_state)["regime_flip_direction"] == "bearish"


@pytest.mark.asyncio
async def test_flip_exits_when_shock_recovers(db) -> None:
    """La posizione flip si chiude da sola appena lo shock che l'ha aperta rientra."""
    _set_regime("BLOCKED", "bearish")
    flip = _position("short")
    flip.position_id = "flip_pos"
    flip.smart_sl_state = json.dumps({"regime_flip_direction": "bearish"})
    ms = _mobile_settings(perp_regime_flip_enabled=True)

    _set_regime("NORMAL", None)
    await _tick(flip, Decimal("100"), ms)

    assert flip.status == "closed"

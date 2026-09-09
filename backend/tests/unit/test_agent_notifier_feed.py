"""Test d'integrazione: AgentNotifier._record scrive nel feed notifiche."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.repositories.notifications import NotificationRepository
from backend.app.notifications.agent_notifier import AgentNotifier

USER = "00000000-0000-0000-0000-000000000001"


def _make_settings(*, fcm_enabled: bool = False) -> MagicMock:
    s = MagicMock()
    s.fcm_enabled = fcm_enabled
    s.fcm_token_store_path = "backend/storage/fcm_tokens.json"
    s.notify_dry_run_trades = True
    s.fcm_spot_topic = "cryptosentinel-spot"
    s.fcm_perp_topic = "cryptosentinel-perp"
    s.fcm_risk_topic = "cryptosentinel-risk"
    s.fcm_summary_topic = "cryptosentinel-summary"
    s.fcm_critical_topic = "cryptosentinel-critical"
    return s


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await init_db(url)
    yield
    await close_db()


async def _feed_items() -> list:
    factory = get_session_factory()
    async with factory() as session:
        repo = NotificationRepository(session)
        return await repo.list(limit=100)


# ------------------------------------------------------------------
# Test: ogni notify_* scrive nel feed anche con FCM disabilitato
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trade_opened_records_to_feed(db) -> None:
    notifier = AgentNotifier(_make_settings())
    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        await notifier.notify_trade_opened(
            user_id=USER, trade_id="t1", asset="BTC", market="spot",
            direction="buy", entry_price=Decimal("60000"), size_usd=Decimal("100"),
            stop_loss=Decimal("58000"), is_dry_run=False,
        )

    items = await _feed_items()
    assert len(items) == 1
    assert items[0].category == "spot_trade"
    assert items[0].severity == "critical"
    assert "BTC" in items[0].title
    assert items[0].link_type == "trade"
    assert items[0].link_ref == "spot:t1"
    assert items[0].data_json["trade_id"] == "t1"


@pytest.mark.asyncio
async def test_trade_closed_records_to_feed(db) -> None:
    notifier = AgentNotifier(_make_settings())
    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        await notifier.notify_trade_closed(
            user_id=USER, trade_id="t2", asset="ETH", market="perp",
            pnl_usd=Decimal("15.50"), pnl_pct=Decimal("3.2"),
            close_reason="take_profit_1",
        )

    items = await _feed_items()
    assert len(items) == 1
    assert items[0].category == "perp_trade"
    assert items[0].link_ref == "perp:t2"
    assert "15.50" in items[0].body


@pytest.mark.asyncio
async def test_risk_alert_records_to_feed(db) -> None:
    notifier = AgentNotifier(_make_settings())
    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        await notifier.notify_risk_alert(USER, "drawdown", "Drawdown 12%")

    items = await _feed_items()
    assert len(items) == 1
    assert items[0].category == "risk"
    assert items[0].severity == "critical"


@pytest.mark.asyncio
async def test_daily_summary_records_to_feed(db) -> None:
    notifier = AgentNotifier(_make_settings())
    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        await notifier.notify_daily_summary(
            user_id=USER, spot_trades=3, perp_trades=1,
            daily_pnl_usd=Decimal("42"), win_rate_pct=75.0,
        )

    items = await _feed_items()
    assert len(items) == 1
    assert items[0].category == "summary"
    assert items[0].severity == "info"


@pytest.mark.asyncio
async def test_reserve_event_records_to_feed(db) -> None:
    notifier = AgentNotifier(_make_settings())
    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        await notifier.notify_reserve_event(USER, "sweep", "Sweep 15$ verso BTC")

    items = await _feed_items()
    assert len(items) == 1
    assert items[0].category == "reserve"
    assert items[0].severity == "normal"


@pytest.mark.asyncio
async def test_agent_critical_records_to_feed(db) -> None:
    notifier = AgentNotifier(_make_settings())
    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value", return_value=None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        await notifier.notify_agent_critical(USER, "degraded", "Binance API timeout")

    items = await _feed_items()
    assert len(items) == 1
    assert items[0].category == "system"
    assert items[0].severity == "critical"


@pytest.mark.asyncio
async def test_record_survives_even_when_pref_blocks_fcm(db) -> None:
    """Se la preferenza blocca FCM (es. spot_trades=False), _record viene
    chiamato PRIMA del gate, quindi l'evento compare comunque nel feed.

    Nota: il gate sulle preferenze è pre-_record per design (evitare rumore
    nel feed). Verifichiamo che il feed resta vuoto quando la pref è off."""
    import json
    notifier = AgentNotifier(_make_settings())
    prefs_json = json.dumps({"spot_trades": False})

    with (
        patch("backend.app.notifications.agent_notifier.get_runtime_value",
              lambda u, k: prefs_json if k == "notification_preferences" else None),
        patch("backend.app.notifications.agent_notifier.set_runtime_value"),
    ):
        result = await notifier.notify_trade_opened(
            user_id=USER, trade_id="t_blocked", asset="BTC", market="spot",
            direction="buy", entry_price=Decimal("60000"), size_usd=Decimal("100"),
            stop_loss=None, is_dry_run=False,
        )

    # Il gate delle preferenze è PRIMA di _record, quindi il feed è vuoto
    assert result is False
    items = await _feed_items()
    assert len(items) == 0

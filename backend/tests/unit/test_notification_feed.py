"""Tests for the notification feed model and repository (Phase 1)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.app.persistence import database
from backend.app.persistence.database import close_db, get_session_factory, init_db
from backend.app.persistence.repositories.notifications import (
    MAX_ROWS,
    RETENTION_DAYS,
    NotificationRepository,
)

USER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
async def db(tmp_path: Path):
    database._engine = None
    database._session_factory = None
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    await init_db(url)
    yield
    await close_db()


async def _repo() -> NotificationRepository:
    factory = get_session_factory()
    session = factory()
    return NotificationRepository(session)


async def _append(repo: NotificationRepository, **overrides) -> None:
    defaults = dict(
        user_id=USER,
        category="spot_trade",
        severity="normal",
        title="Trade aperto",
        body="LONG BTC @ 60000",
    )
    defaults.update(overrides)
    await repo.append(**defaults)


# ------------------------------------------------------------------
# append + list base
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_and_list(db) -> None:
    repo = await _repo()
    evt = await repo.append(
        user_id=USER,
        category="spot_trade",
        severity="normal",
        title="Test",
        body="Body",
        data_json={"trade_id": "t1"},
        link_type="trade",
        link_ref="spot:t1",
    )
    assert evt.event_id
    assert evt.read_at is None

    items = await repo.list()
    assert len(items) == 1
    assert items[0].event_id == evt.event_id
    assert items[0].data_json == {"trade_id": "t1"}
    assert items[0].link_type == "trade"


@pytest.mark.asyncio
async def test_list_descending_order(db) -> None:
    repo = await _repo()
    await _append(repo, title="First")
    await _append(repo, title="Second")
    await _append(repo, title="Third")

    items = await repo.list()
    assert [i.title for i in items] == ["Third", "Second", "First"]


# ------------------------------------------------------------------
# since / before cursors
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_since_cursor(db) -> None:
    repo = await _repo()
    e1 = await repo.append(user_id=USER, category="risk", severity="critical", title="A", body="a")
    e2 = await repo.append(user_id=USER, category="risk", severity="critical", title="B", body="b")
    e3 = await repo.append(user_id=USER, category="risk", severity="critical", title="C", body="c")

    # since=e1 → dovrebbe restituire e2, e3 in ordine crescente (polling)
    newer = await repo.list(since=e1.event_id)
    assert [e.title for e in newer] == ["B", "C"]


@pytest.mark.asyncio
async def test_before_cursor(db) -> None:
    repo = await _repo()
    e1 = await repo.append(user_id=USER, category="risk", severity="critical", title="A", body="a")
    e2 = await repo.append(user_id=USER, category="risk", severity="critical", title="B", body="b")
    e3 = await repo.append(user_id=USER, category="risk", severity="critical", title="C", body="c")

    # before=e3 → restituisce e2, e1 in ordine decrescente (paginazione)
    older = await repo.list(before=e3.event_id)
    assert [e.title for e in older] == ["B", "A"]


@pytest.mark.asyncio
async def test_since_invalid_cursor_returns_all(db) -> None:
    repo = await _repo()
    await _append(repo, title="X")
    items = await repo.list(since="nonexistent")
    # cursore non trovato: restituisce come se since non ci fosse
    assert len(items) == 1


# ------------------------------------------------------------------
# Filtri
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_category(db) -> None:
    repo = await _repo()
    await _append(repo, category="spot_trade")
    await _append(repo, category="risk")
    await _append(repo, category="reserve")

    items = await repo.list(categories=["risk", "reserve"])
    assert len(items) == 2
    assert all(i.category in ("risk", "reserve") for i in items)


@pytest.mark.asyncio
async def test_filter_by_severity(db) -> None:
    repo = await _repo()
    await _append(repo, severity="info")
    await _append(repo, severity="critical")

    items = await repo.list(severities=["critical"])
    assert len(items) == 1
    assert items[0].severity == "critical"


@pytest.mark.asyncio
async def test_filter_unread_only(db) -> None:
    repo = await _repo()
    await _append(repo, title="Unread")
    e2 = await repo.append(user_id=USER, category="risk", severity="normal", title="Read", body="x")
    await repo.mark_read(ids=[e2.event_id])

    items = await repo.list(unread_only=True)
    assert len(items) == 1
    assert items[0].title == "Unread"


@pytest.mark.asyncio
async def test_filter_text_search(db) -> None:
    repo = await _repo()
    await _append(repo, title="Trade aperto BTC", body="LONG")
    await _append(repo, title="Allarme rischio", body="drawdown 12%")

    items = await repo.list(q="BTC")
    assert len(items) == 1
    assert "BTC" in items[0].title


@pytest.mark.asyncio
async def test_limit(db) -> None:
    repo = await _repo()
    for i in range(10):
        await _append(repo, title=f"E{i}")

    items = await repo.list(limit=3)
    assert len(items) == 3


# ------------------------------------------------------------------
# unread_count
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unread_count(db) -> None:
    repo = await _repo()
    await _append(repo)
    await _append(repo)
    assert await repo.unread_count() == 2


# ------------------------------------------------------------------
# mark_read
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_read_by_ids(db) -> None:
    repo = await _repo()
    e1 = await repo.append(user_id=USER, category="risk", severity="normal", title="A", body="a")
    e2 = await repo.append(user_id=USER, category="risk", severity="normal", title="B", body="b")

    remaining = await repo.mark_read(ids=[e1.event_id])
    assert remaining == 1

    items = await repo.list(unread_only=True)
    assert len(items) == 1
    assert items[0].event_id == e2.event_id


@pytest.mark.asyncio
async def test_mark_read_all(db) -> None:
    repo = await _repo()
    await _append(repo)
    await _append(repo)
    await _append(repo)

    remaining = await repo.mark_read(all=True)
    assert remaining == 0
    assert await repo.unread_count() == 0


# ------------------------------------------------------------------
# prune
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_old_events(db) -> None:
    """Eventi più vecchi di RETENTION_DAYS vengono eliminati."""
    repo = await _repo()
    factory = get_session_factory()

    # Inserisci un evento e forza created_at nel passato
    evt = await repo.append(user_id=USER, category="system", severity="info", title="Old", body="old")
    async with factory() as session:
        from sqlalchemy import update
        from backend.app.persistence.models.notifications import NotificationEvent
        old_date = datetime.now(UTC) - timedelta(days=RETENTION_DAYS + 1)
        await session.execute(
            update(NotificationEvent)
            .where(NotificationEvent.event_id == evt.event_id)
            .values(created_at=old_date)
        )
        await session.commit()

    await _append(repo, title="Recent")

    deleted = await repo.prune()
    assert deleted >= 1

    items = await repo.list()
    assert len(items) == 1
    assert items[0].title == "Recent"


@pytest.mark.asyncio
async def test_prune_excess_rows(db) -> None:
    """Se ci sono più di MAX_ROWS, le più vecchie vengono eliminate."""
    repo = await _repo()
    # MAX_ROWS è 2000, non possiamo inserirne 2000+ in test rapido.
    # Testiamo con un monkey-patch temporaneo.
    import backend.app.persistence.repositories.notifications as mod
    original_max = mod.MAX_ROWS
    mod.MAX_ROWS = 5
    try:
        for i in range(8):
            await _append(repo, title=f"E{i}")

        deleted = await repo.prune()
        assert deleted == 3  # 8 - 5

        items = await repo.list()
        assert len(items) == 5
        # Le righe sopravvissute sono le 5 più recenti (E3..E7)
        titles = [i.title for i in items]
        assert "E7" in titles
        assert "E3" in titles
        assert "E2" not in titles
    finally:
        mod.MAX_ROWS = original_max

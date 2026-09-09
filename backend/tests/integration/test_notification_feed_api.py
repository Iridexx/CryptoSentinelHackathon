"""Integration test per gli endpoint del feed notifiche dashboard (fase 3)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from types import SimpleNamespace
from uuid import UUID

from backend.app.api.dependencies import require_read_access
from backend.app.core.config import Settings, get_settings
from backend.app.api.routes.notifications import router
from backend.app.persistence.database import close_db, get_session, get_session_factory, init_db
from backend.app.persistence.repositories.notifications import NotificationRepository
from backend.app.persistence.sync_database import create_all_sync, init_sync_db, reset_sync_db


@pytest_asyncio.fixture
async def feed_app(tmp_path: Path):
    await close_db()
    reset_sync_db()
    db_path = tmp_path / "feed.db"
    await init_db(f"sqlite+aiosqlite:///{db_path}")
    init_sync_db(f"sqlite:///{db_path}")
    create_all_sync()

    async def _session_override():
        async with get_session_factory()() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    fake_settings = SimpleNamespace(default_user_id=UUID("00000000-0000-0000-0000-000000000001"))

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_read_access] = lambda: None
    app.dependency_overrides[get_settings] = lambda: fake_settings
    yield app
    await close_db()
    reset_sync_db()


async def _seed(n: int = 3) -> list[str]:
    """Inserisce n eventi nel feed, restituisce event_id in ordine di creazione."""
    factory = get_session_factory()
    ids = []
    async with factory() as session:
        repo = NotificationRepository(session)
        for i in range(n):
            evt = await repo.append(
                user_id="00000000-0000-0000-0000-000000000001",
                category=["spot_trade", "risk", "reserve"][i % 3],
                severity=["critical", "normal", "info"][i % 3],
                title=f"Evento {i}",
                body=f"Body {i}",
                data_json={"index": str(i)},
            )
            ids.append(evt.event_id)
    return ids


# ------------------------------------------------------------------
# GET /feed
# ------------------------------------------------------------------

def test_feed_empty(feed_app: FastAPI) -> None:
    client = TestClient(feed_app)
    resp = client.get("/api/v1/notifications/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["unread_count"] == 0
    assert data["cursor"] is None


@pytest.mark.asyncio
async def test_feed_returns_items(feed_app: FastAPI) -> None:
    ids = await _seed(3)
    client = TestClient(feed_app)
    resp = client.get("/api/v1/notifications/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 3
    assert data["unread_count"] == 3
    # Ordine decrescente (più recente in cima)
    assert data["items"][0]["title"] == "Evento 2"
    assert data["items"][2]["title"] == "Evento 0"


@pytest.mark.asyncio
async def test_feed_since_cursor(feed_app: FastAPI) -> None:
    ids = await _seed(5)
    client = TestClient(feed_app)
    # since=ids[2] → eventi dopo il terzo (indice 3 e 4), ordine crescente
    resp = client.get(f"/api/v1/notifications/feed?since={ids[2]}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["title"] == "Evento 3"
    assert items[1]["title"] == "Evento 4"


@pytest.mark.asyncio
async def test_feed_before_cursor(feed_app: FastAPI) -> None:
    ids = await _seed(5)
    client = TestClient(feed_app)
    resp = client.get(f"/api/v1/notifications/feed?before={ids[2]}")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    titles = [i["title"] for i in items]
    assert titles == ["Evento 1", "Evento 0"]


@pytest.mark.asyncio
async def test_feed_filter_category(feed_app: FastAPI) -> None:
    await _seed(6)
    client = TestClient(feed_app)
    resp = client.get("/api/v1/notifications/feed?categories=risk")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["category"] == "risk" for i in items)
    assert len(items) == 2  # indices 1 and 4


@pytest.mark.asyncio
async def test_feed_filter_unread_only(feed_app: FastAPI) -> None:
    ids = await _seed(3)
    client = TestClient(feed_app)
    # Segna il primo come letto
    client.post("/api/v1/notifications/feed/read", json={"ids": [ids[0]]})
    resp = client.get("/api/v1/notifications/feed?unread_only=true")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2


@pytest.mark.asyncio
async def test_feed_text_search(feed_app: FastAPI) -> None:
    await _seed(3)
    client = TestClient(feed_app)
    resp = client.get("/api/v1/notifications/feed?q=Evento+1")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Evento 1"


@pytest.mark.asyncio
async def test_feed_limit(feed_app: FastAPI) -> None:
    await _seed(5)
    client = TestClient(feed_app)
    resp = client.get("/api/v1/notifications/feed?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


# ------------------------------------------------------------------
# POST /feed/read
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_read_by_ids(feed_app: FastAPI) -> None:
    ids = await _seed(3)
    client = TestClient(feed_app)
    resp = client.post("/api/v1/notifications/feed/read", json={"ids": [ids[0], ids[1]]})
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 1


@pytest.mark.asyncio
async def test_mark_read_all(feed_app: FastAPI) -> None:
    await _seed(5)
    client = TestClient(feed_app)
    resp = client.post("/api/v1/notifications/feed/read", json={"all": True})
    assert resp.status_code == 200
    assert resp.json()["unread_count"] == 0


# ------------------------------------------------------------------
# GET/PUT /toast-prefs
# ------------------------------------------------------------------

def test_toast_prefs_default(feed_app: FastAPI) -> None:
    client = TestClient(feed_app)
    resp = client.get("/api/v1/notifications/toast-prefs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "default"
    prefs = data["preferences"]
    assert prefs["toast_spot_trade"] is True
    assert prefs["toast_reserve"] is False
    assert prefs["toast_summary"] is False


def test_toast_prefs_update_round_trip(feed_app: FastAPI) -> None:
    client = TestClient(feed_app)
    new_prefs = {
        "toast_spot_trade": False,
        "toast_perp_trade": True,
        "toast_risk": True,
        "toast_system": True,
        "toast_reserve": True,
        "toast_summary": False,
    }
    put_resp = client.put("/api/v1/notifications/toast-prefs", json=new_prefs)
    assert put_resp.status_code == 200
    assert put_resp.json()["source"] == "persisted"
    assert put_resp.json()["preferences"]["toast_spot_trade"] is False
    assert put_resp.json()["preferences"]["toast_reserve"] is True

    get_resp = client.get("/api/v1/notifications/toast-prefs")
    assert get_resp.status_code == 200
    assert get_resp.json()["preferences"]["toast_spot_trade"] is False
    assert get_resp.json()["preferences"]["toast_reserve"] is True

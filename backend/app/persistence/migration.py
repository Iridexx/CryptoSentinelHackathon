"""Startup migrations: JSON-to-DB data import + idempotent schema upgrades.

Run automatically at startup by main.py lifespan.  Both functions are
idempotent — safe to call on every restart.  JSON files are left on disk as
emergency reference but are no longer used by the application.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.repositories.alerts import AlertConfigRepository
from backend.app.persistence.repositories.device_tokens import DeviceTokenRepository

logger = structlog.get_logger("persistence.migration")

_DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


async def upgrade_schema(session: AsyncSession) -> None:
    """Idempotent DDL upgrades — adds missing columns to existing tables.

    SQLite supports ALTER TABLE ADD COLUMN for nullable and DEFAULT-bearing
    columns.  We check PRAGMA table_info before each ADD to stay idempotent.
    """

    async def _has_column(table: str, column: str) -> bool:
        result = await session.execute(text(f"PRAGMA table_info({table})"))
        return any(row[1] == column for row in result.fetchall())

    # ── perp_positions ────────────────────────────────────────────────────────
    perp_pos_cols: list[tuple[str, str]] = [
        ("fee_mode",            "VARCHAR(8)"),
        ("margin_usd",          "NUMERIC(20, 8)"),
        ("opening_fee_usd",     "NUMERIC(20, 8)"),
        ("taker_fee_usd",       "NUMERIC(20, 8)"),
        ("maker_fee_usd",       "NUMERIC(20, 8)"),
        ("slippage_usd",        "NUMERIC(20, 8)"),
        ("funding_accrued_usd", "NUMERIC(20, 8) NOT NULL DEFAULT 0"),
    ]
    for col, defn in perp_pos_cols:
        if not await _has_column("perp_positions", col):
            await session.execute(
                text(f"ALTER TABLE perp_positions ADD COLUMN {col} {defn}")
            )
            logger.info("schema_column_added", table="perp_positions", column=col)

    # ── perp_trades ───────────────────────────────────────────────────────────
    perp_trade_cols: list[tuple[str, str]] = [
        ("fee_mode",        "VARCHAR(8)"),
        ("taker_fee_usd",   "NUMERIC(20, 8)"),
        ("maker_fee_usd",   "NUMERIC(20, 8)"),
        ("slippage_usd",    "NUMERIC(20, 8)"),
        ("funding_rate_8h", "NUMERIC(20, 10)"),
    ]
    for col, defn in perp_trade_cols:
        if not await _has_column("perp_trades", col):
            await session.execute(
                text(f"ALTER TABLE perp_trades ADD COLUMN {col} {defn}")
            )
            logger.info("schema_column_added", table="perp_trades", column=col)

    # ── spot_positions ────────────────────────────────────────────────────────
    spot_pos_cols: list[tuple[str, str]] = [
        ("fee_mode",       "VARCHAR(8)"),
        ("swap_fee_usd",   "NUMERIC(20, 8)"),
        ("slippage_usd",   "NUMERIC(20, 8)"),
        ("entry_atr",      "NUMERIC(30, 8)"),
        ("max_price",      "NUMERIC(30, 8)"),
        ("scale_in_count", "INTEGER NOT NULL DEFAULT 0"),
    ]
    for col, defn in spot_pos_cols:
        if not await _has_column("spot_positions", col):
            await session.execute(
                text(f"ALTER TABLE spot_positions ADD COLUMN {col} {defn}")
            )
            logger.info("schema_column_added", table="spot_positions", column=col)

    # ── spot_trades ───────────────────────────────────────────────────────────
    spot_trade_cols: list[tuple[str, str]] = [
        ("fee_mode",     "VARCHAR(8)"),
        ("swap_fee_usd", "NUMERIC(20, 8)"),
        ("slippage_usd", "NUMERIC(20, 8)"),
    ]
    for col, defn in spot_trade_cols:
        if not await _has_column("spot_trades", col):
            await session.execute(
                text(f"ALTER TABLE spot_trades ADD COLUMN {col} {defn}")
            )
            logger.info("schema_column_added", table="spot_trades", column=col)

    await session.commit()


async def migrate_json_to_db(
    session: AsyncSession,
    *,
    fcm_tokens_path: str = "backend/storage/fcm_tokens.json",
    alerts_path: str = "backend/storage/alerts.json",
) -> None:
    """Copy JSON-backed stores into DB if the target tables are empty."""

    await _migrate_fcm_tokens(session, Path(fcm_tokens_path))
    await _migrate_alerts(session, Path(alerts_path))


async def _migrate_fcm_tokens(session: AsyncSession, path: Path) -> None:
    repo = DeviceTokenRepository(session)
    if await repo.count() > 0:
        return
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("tokens", []):
            if "token_id" not in item or "token" not in item:
                continue
            from datetime import UTC, datetime

            created = _parse_dt(item.get("created_at")) or datetime.now(UTC)
            updated = _parse_dt(item.get("updated_at")) or datetime.now(UTC)
            from backend.app.persistence.models.device_tokens import DeviceToken

            record = DeviceToken(
                token_id=item["token_id"],
                token=item["token"],
                user_id=item.get("user_id", _DEFAULT_USER_ID),
                platform=item.get("platform", "android"),
                device_id=item.get("device_id"),
                app_version=item.get("app_version"),
                locale=item.get("locale"),
                created_at=created,
                updated_at=updated,
            )
            session.add(record)
        await session.commit()
        logger.info("fcm_tokens_migrated", source=str(path))
    except Exception as exc:
        logger.warning("fcm_tokens_migration_failed", error=str(exc))
        await session.rollback()


async def _migrate_alerts(session: AsyncSession, path: Path) -> None:
    repo = AlertConfigRepository(session)
    existing_config, existing_state = await repo.load(_DEFAULT_USER_ID)
    if existing_config is not None:
        return
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        config = data.get("config")
        state = data.get("state", {})
        await repo.save(_DEFAULT_USER_ID, config, state)
        logger.info("alerts_migrated", source=str(path))
    except Exception as exc:
        logger.warning("alerts_migration_failed", error=str(exc))


def _parse_dt(value: str | None):
    if not value:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None

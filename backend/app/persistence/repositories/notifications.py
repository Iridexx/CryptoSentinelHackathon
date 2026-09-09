"""Repository for the dashboard notification feed."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.notifications import NotificationEvent

RETENTION_DAYS = 30
MAX_ROWS = 2000


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def append(
        self,
        *,
        user_id: str,
        category: str,
        severity: str,
        title: str,
        body: str,
        data_json: dict | None = None,
        link_type: str | None = None,
        link_ref: str | None = None,
    ) -> NotificationEvent:
        """Inserisce un nuovo evento nel feed e restituisce la riga."""
        now = datetime.now(UTC)
        event = NotificationEvent(
            event_id=uuid4().hex,
            user_id=user_id,
            category=category,
            severity=severity,
            title=title,
            body=body,
            data_json=data_json,
            link_type=link_type,
            link_ref=link_ref,
            created_at=now,
            read_at=None,
        )
        self._session.add(event)
        await self._session.commit()
        return event

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list(
        self,
        *,
        user_id: str | None = None,
        since: str | None = None,
        before: str | None = None,
        categories: list[str] | None = None,
        severities: list[str] | None = None,
        unread_only: bool = False,
        q: str | None = None,
        limit: int = 50,
    ) -> list[NotificationEvent]:
        """Restituisce eventi in ordine decrescente (più recente in cima).

        ``since``  = event_id cursore → eventi **più recenti** del cursore.
        ``before`` = event_id cursore → eventi **più vecchi** del cursore (paginazione indietro).
        """
        stmt = select(NotificationEvent)
        if user_id:
            stmt = stmt.where(NotificationEvent.user_id == user_id)
        if categories:
            stmt = stmt.where(NotificationEvent.category.in_(categories))
        if severities:
            stmt = stmt.where(NotificationEvent.severity.in_(severities))
        if unread_only:
            stmt = stmt.where(NotificationEvent.read_at.is_(None))
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                NotificationEvent.title.ilike(pattern)
                | NotificationEvent.body.ilike(pattern)
            )

        if since:
            ref = await self._resolve_cursor(since)
            if ref:
                stmt = stmt.where(
                    (NotificationEvent.created_at > ref.created_at)
                    | (
                        (NotificationEvent.created_at == ref.created_at)
                        & (NotificationEvent.id > ref.id)
                    )
                )
                # Quando si chiede "dopo il cursore", si vuole ordine crescente
                # così il caller vede gli eventi dal più vecchio al più recente
                # e può generare i toast nell'ordine giusto.
                stmt = stmt.order_by(NotificationEvent.created_at.asc(), NotificationEvent.id.asc())
                stmt = stmt.limit(limit)
                result = await self._session.execute(stmt)
                return list(result.scalars().all())

        if before:
            ref = await self._resolve_cursor(before)
            if ref:
                stmt = stmt.where(
                    (NotificationEvent.created_at < ref.created_at)
                    | (
                        (NotificationEvent.created_at == ref.created_at)
                        & (NotificationEvent.id < ref.id)
                    )
                )

        stmt = stmt.order_by(NotificationEvent.created_at.desc(), NotificationEvent.id.desc())
        stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def unread_count(self, *, user_id: str | None = None) -> int:
        stmt = select(func.count(NotificationEvent.id)).where(
            NotificationEvent.read_at.is_(None)
        )
        if user_id:
            stmt = stmt.where(NotificationEvent.user_id == user_id)
        result = await self._session.execute(stmt)
        return int(result.scalar_one() or 0)

    # ------------------------------------------------------------------
    # Mark read
    # ------------------------------------------------------------------

    async def mark_read(
        self,
        *,
        ids: list[str] | None = None,
        all: bool = False,
        before: str | None = None,
    ) -> int:
        """Segna come letti e restituisce il nuovo unread_count globale."""
        now = datetime.now(UTC)
        if all:
            stmt = (
                select(NotificationEvent)
                .where(NotificationEvent.read_at.is_(None))
            )
            if before:
                ref = await self._resolve_cursor(before)
                if ref:
                    stmt = stmt.where(NotificationEvent.created_at <= ref.created_at)
            rows = (await self._session.execute(stmt)).scalars().all()
            for row in rows:
                row.read_at = now
        elif ids:
            stmt = (
                select(NotificationEvent)
                .where(NotificationEvent.event_id.in_(ids))
                .where(NotificationEvent.read_at.is_(None))
            )
            rows = (await self._session.execute(stmt)).scalars().all()
            for row in rows:
                row.read_at = now
        await self._session.commit()
        return await self.unread_count()

    # ------------------------------------------------------------------
    # Prune
    # ------------------------------------------------------------------

    async def prune(self) -> int:
        """Elimina eventi vecchi (>30g) e in eccesso (>2000). Restituisce righe eliminate."""
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
        stmt_age = delete(NotificationEvent).where(
            NotificationEvent.created_at < cutoff
        )
        result_age = await self._session.execute(stmt_age)
        deleted = result_age.rowcount or 0

        total = int(
            (await self._session.execute(select(func.count(NotificationEvent.id)))).scalar_one() or 0
        )
        if total > MAX_ROWS:
            excess = total - MAX_ROWS
            oldest_ids_stmt = (
                select(NotificationEvent.id)
                .order_by(NotificationEvent.created_at.asc(), NotificationEvent.id.asc())
                .limit(excess)
            )
            oldest_ids = [
                row[0] for row in (await self._session.execute(oldest_ids_stmt)).all()
            ]
            if oldest_ids:
                stmt_excess = delete(NotificationEvent).where(
                    NotificationEvent.id.in_(oldest_ids)
                )
                result_excess = await self._session.execute(stmt_excess)
                deleted += result_excess.rowcount or 0

        await self._session.commit()
        return deleted

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _resolve_cursor(self, event_id: str) -> NotificationEvent | None:
        stmt = select(NotificationEvent).where(
            NotificationEvent.event_id == event_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

"""ORM model for the dashboard notification feed."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class NotificationEvent(Base):
    """Riga del feed notifiche dashboard.

    Ogni evento generato dall'AgentNotifier (trade, rischio, riserva, sistema,
    riepilogo) scrive una riga qui — indipendentemente da FCM — così il
    dashboard può mostrare toast e una timeline storica.
    """

    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    link_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    link_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

from datetime import datetime, timezone
from sqlalchemy import String, DateTime, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ChannelEvent(Base):
    __tablename__ = "channel_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_channel_event_provider_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    applicant_lead_id: Mapped[int | None] = mapped_column(ForeignKey("applicant_leads.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(30), default="website")
    language: Mapped[str] = mapped_column(String(10), default="en")
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Destination metadata is stored per conversation so staff replies return to its original channel/thread.
    channel_destination: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_user_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def has_unread_response(self) -> bool:
        if self.last_response_at is None:
            return False
        if self.last_user_read_at is None:
            return True
        response_at = self.last_response_at
        read_at = self.last_user_read_at
        if response_at.tzinfo is None and read_at.tzinfo is not None:
            response_at = response_at.replace(tzinfo=timezone.utc)
        if read_at.tzinfo is None and response_at.tzinfo is not None:
            read_at = read_at.replace(tzinfo=timezone.utc)
        return response_at > read_at

    user: Mapped["User | None"] = relationship(back_populates="conversations")
    applicant_lead = relationship("ApplicantLead")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")

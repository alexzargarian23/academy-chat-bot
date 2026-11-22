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
    applicant_lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("applicant_leads.id"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(30), default="website")
    language: Mapped[str] = mapped_column(String(10), default="en")
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Timestamp of the most recent staff-authored message visible to the user.
    last_staff_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # Updated whenever the owner opens the conversation's messages.
    last_user_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def has_unread_staff_message(self) -> bool:
        if self.last_staff_message_at is None:
            return False
        if self.last_user_read_at is None:
            return True
        staff_at = self.last_staff_message_at
        read_at = self.last_user_read_at
        # PostgreSQL normally returns aware timestamps; normalize SQLite/test values too.
        if staff_at.tzinfo is None and read_at.tzinfo is not None:
            staff_at = staff_at.replace(tzinfo=timezone.utc)
        if read_at.tzinfo is None and staff_at.tzinfo is not None:
            read_at = read_at.replace(tzinfo=timezone.utc)
        return staff_at > read_at

    user: Mapped["User | None"] = relationship(back_populates="conversations")
    applicant_lead = relationship("ApplicantLead")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

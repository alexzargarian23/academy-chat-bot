from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AcademyEmail(Base):
    __tablename__ = "academy_emails"
    __table_args__ = (UniqueConstraint("message_id", name="uq_academy_email_message_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String(500), nullable=False)
    recipient: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(1000), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reply_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    staff_approved: Mapped[bool] = mapped_column(Boolean, default=False)

    approver = relationship("User", foreign_keys=[approved_by])
    gmail_thread_id: Mapped[str | None] = mapped_column(
        String(500), nullable=True, index=True
    )

    rfc_message_id: Mapped[str | None] = mapped_column(
        String(1000), nullable=True
    )

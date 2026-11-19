
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ApplicantLead(Base):
    __tablename__ = "applicant_leads"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_applicant_leads_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(40), default="")

    interested_program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id"),
        nullable=True
    )

    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(
        String(40), default="website_registration"
    )
    contact_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    qualification_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # new, contacted, qualified, converted, rejected
    status: Mapped[str] = mapped_column(
        String(30),
        default="new"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User")

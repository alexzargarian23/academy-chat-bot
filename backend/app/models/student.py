
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_student_profile_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    student_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True
    )

    program_id: Mapped[int | None] = mapped_column(
        ForeignKey("programs.id"),
        nullable=True
    )

    phone: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True
    )

    academic_year: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True
    )

    enrollment_status: Mapped[str] = mapped_column(
        String(30),
        default="active"
    )

    enrollment_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", backref="student_profile")
    program = relationship("Program")

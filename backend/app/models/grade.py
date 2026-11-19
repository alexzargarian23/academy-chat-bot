from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StudentGrade(Base):
    __tablename__ = "student_grades"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_profile_id: Mapped[int] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    schedule_id: Mapped[int] = mapped_column(
        ForeignKey("class_schedules.id"),
        nullable=False,
        index=True,
    )

    assessment_name: Mapped[str] = mapped_column(String(200), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    max_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    letter_grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    academic_year: Mapped[str] = mapped_column(String(30), nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    graded_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    graded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    student_profile = relationship("StudentProfile")
    schedule = relationship("ClassSchedule")
    grader = relationship("User")

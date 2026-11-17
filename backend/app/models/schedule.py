
from datetime import date, datetime, time, timezone

from sqlalchemy import (
    String,
    Text,
    DateTime,
    Date,
    Time,
    Boolean,
    ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ClassSchedule(Base):
    __tablename__ = "class_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)

    program_id: Mapped[int] = mapped_column(
        ForeignKey("programs.id"),
        nullable=False,
        index=True
    )

    course_name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True
    )

    academic_year: Mapped[str] = mapped_column(String(30))
    day_of_week: Mapped[str] = mapped_column(String(10))

    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    instructor: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True
    )

    room: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    effective_from: Mapped[date] = mapped_column(
        Date,
        default=date.today
    )

    effective_until: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    program = relationship("Program")

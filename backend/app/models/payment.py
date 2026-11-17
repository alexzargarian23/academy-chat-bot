
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String,
    Text,
    DateTime,
    Date,
    ForeignKey,
    Numeric
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StudentInvoice(Base):
    __tablename__ = "student_invoices"

    id: Mapped[int] = mapped_column(primary_key=True)

    student_profile_id: Mapped[int] = mapped_column(
        ForeignKey("student_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    description: Mapped[str] = mapped_column(Text)
    academic_year: Mapped[str] = mapped_column(String(30))

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD"
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True
    )

    # unpaid, partially_paid, paid, cancelled
    status: Mapped[str] = mapped_column(
        String(30),
        default="unpaid"
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    student_profile = relationship("StudentProfile")

    payments = relationship(
        "StudentPayment",
        back_populates="invoice",
        cascade="all, delete-orphan"
    )


class StudentPayment(Base):
    __tablename__ = "student_payments"

    id: Mapped[int] = mapped_column(primary_key=True)

    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("student_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False
    )

    method: Mapped[str] = mapped_column(String(30))

    reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    paid_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc)
    )

    received_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False
    )

    invoice = relationship(
        "StudentInvoice",
        back_populates="payments"
    )

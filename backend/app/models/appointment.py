from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_appointment_slot_positive_duration"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    staff_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    staff = relationship("User", foreign_keys=[staff_user_id])
    creator = relationship("User", foreign_keys=[created_by])
    appointments = relationship("Appointment", back_populates="slot")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int] = mapped_column(ForeignKey("appointment_slots.id"), nullable=False, index=True)
    student_profile_id: Mapped[int | None] = mapped_column(ForeignKey("student_profiles.id", ondelete="CASCADE"), nullable=True, index=True)
    applicant_lead_id: Mapped[int | None] = mapped_column(ForeignKey("applicant_leads.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="booked", index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    staff_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    slot = relationship("AppointmentSlot", back_populates="appointments")
    student_profile = relationship("StudentProfile")
    applicant_lead = relationship("ApplicantLead")
    creator = relationship("User", foreign_keys=[created_by])

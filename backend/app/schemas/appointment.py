from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

AppointmentStatus = Literal["booked", "cancelled", "completed", "no_show"]

class AppointmentSlotCreate(BaseModel):
    appointment_type: str = Field(min_length=2, max_length=100)
    starts_at: datetime
    ends_at: datetime
    staff_user_id: int | None = Field(default=None, gt=0)
    location: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def valid_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Appointment datetimes must include a timezone offset")
        return self

class AppointmentBook(BaseModel):
    slot_id: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=1000)

class AppointmentStaffUpdate(BaseModel):
    status: Literal["completed", "no_show", "cancelled"] | None = None
    staff_notes: str | None = Field(default=None, max_length=5000)

class AppointmentSlotResponse(BaseModel):
    id: int
    appointment_type: str
    starts_at: datetime
    ends_at: datetime
    staff_user_id: int | None
    staff_name: str | None
    location: str | None
    status: str
    model_config = ConfigDict(from_attributes=True)

class AppointmentResponse(BaseModel):
    id: int
    slot_id: int
    student_profile_id: int
    student_number: str
    student_name: str
    appointment_type: str
    starts_at: datetime
    ends_at: datetime
    staff_name: str | None
    location: str | None
    status: str
    reason: str | None
    staff_notes: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

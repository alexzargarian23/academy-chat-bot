
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


AttendanceStatus = Literal[
    "present",
    "absent",
    "late",
    "excused",
]


class AttendanceCreate(BaseModel):
    student_profile_id: int = Field(gt=0)
    schedule_id: int = Field(gt=0)
    attendance_date: date
    status: AttendanceStatus = "present"
    notes: str | None = Field(default=None, max_length=2000)


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AttendanceResponse(BaseModel):
    id: int
    student_profile_id: int
    student_number: str
    student_name: str
    schedule_id: int
    course_name: str
    program_name: str
    academic_year: str
    attendance_date: date
    status: str
    notes: str | None
    recorded_by: int
    recorded_by_name: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AttendanceSummary(BaseModel):
    student_profile_id: int
    student_number: str
    student_name: str
    total_records: int
    present: int
    absent: int
    late: int
    excused: int
    attendance_percentage: float

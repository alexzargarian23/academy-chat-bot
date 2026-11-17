
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StudentProfileCreate(BaseModel):
    user_id: int = Field(gt=0)
    student_number: str = Field(min_length=1, max_length=50)
    program_id: int | None = None
    phone: str | None = Field(default=None, max_length=40)
    academic_year: str | None = Field(default=None, max_length=30)
    enrollment_status: str = "active"
    enrollment_date: datetime | None = None


class StudentProfileUpdate(BaseModel):
    student_number: str | None = Field(default=None, min_length=1, max_length=50)
    program_id: int | None = None
    phone: str | None = Field(default=None, max_length=40)
    academic_year: str | None = Field(default=None, max_length=30)
    enrollment_status: str | None = None
    enrollment_date: datetime | None = None


class StudentProfileResponse(BaseModel):
    id: int
    user_id: int
    student_number: str
    program_id: int | None
    phone: str | None
    academic_year: str | None
    enrollment_status: str
    enrollment_date: datetime | None
    created_at: datetime
    full_name: str
    email: str
    program_name: str | None

    model_config = ConfigDict(from_attributes=True)

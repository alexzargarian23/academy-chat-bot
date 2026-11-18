from datetime import date, datetime, time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

DayOfWeek = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

class ScheduleCreate(BaseModel):
    program_id: int = Field(gt=0)
    course_name: str = Field(min_length=2, max_length=200)
    description: str | None = None
    academic_year: str = Field(min_length=1, max_length=30)
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    instructor: str | None = Field(default=None, max_length=150)
    room: str | None = Field(default=None, max_length=100)
    effective_from: date = Field(default_factory=date.today)
    effective_until: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_period(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until cannot be before effective_from")
        return self

class ScheduleUpdate(BaseModel):
    program_id: int | None = Field(default=None, gt=0)
    course_name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    academic_year: str | None = Field(default=None, min_length=1, max_length=30)
    day_of_week: DayOfWeek | None = None
    start_time: time | None = None
    end_time: time | None = None
    instructor: str | None = Field(default=None, max_length=150)
    room: str | None = Field(default=None, max_length=100)
    effective_from: date | None = None
    effective_until: date | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.start_time is not None and self.end_time is not None and self.end_time <= self.start_time:
            raise ValueError("end_time must be later than start_time")
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("effective_until cannot be before effective_from")
        return self

class ScheduleResponse(BaseModel):
    id: int
    program_id: int
    program_name: str
    course_name: str
    description: str | None
    academic_year: str
    day_of_week: str
    start_time: time
    end_time: time
    instructor: str | None
    room: str | None
    effective_from: date
    effective_until: date | None
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

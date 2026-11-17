
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApplicantLeadCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str = Field(min_length=5, max_length=40)
    interested_program_id: int | None = None
    message: str | None = Field(default=None, max_length=2000)


class ApplicantLeadResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: str
    interested_program_id: int | None
    message: str | None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicantLeadStatusUpdate(BaseModel):
    status: str

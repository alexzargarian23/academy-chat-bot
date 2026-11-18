from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class StudentRequestCreate(BaseModel):
    category: str = Field(min_length=2, max_length=50)
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=5000)

class StudentRequestStaffUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(pending|in_review|approved|rejected|completed|cancelled)$")
    staff_notes: str | None = Field(default=None, max_length=5000)
    assigned_to: int | None = Field(default=None, gt=0)

class StudentRequestResponse(BaseModel):
    id: int
    student_profile_id: int
    category: str
    subject: str
    description: str
    status: str
    staff_notes: str | None
    assigned_to: int | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)

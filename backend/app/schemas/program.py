
from pydantic import BaseModel, ConfigDict, Field


class ProgramCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5)
    duration: str | None = None
    language: str = "en"
    tuition: str | None = None


class ProgramResponse(ProgramCreate):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

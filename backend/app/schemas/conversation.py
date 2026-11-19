from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ConversationCreate(BaseModel):
    channel: str = "website"
    language: str = "en"


class ConversationResponse(BaseModel):
    id: int
    user_id: int | None
    applicant_lead_id: int | None = None
    channel: str
    language: str
    title: str | None = None
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender: str
    content: str
    sources: list[dict] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

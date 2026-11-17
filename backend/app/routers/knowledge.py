
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.services.retrieval_service import search_knowledge


router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


class KnowledgeSearchRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


@router.post("/search")
def search_documents(
    data: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    results = search_knowledge(
        question=data.question,
        db=db,
        user_role=current_user.role,
        limit=data.limit
    )

    return {
        "question": data.question,
        "results_count": len(results),
        "results": results
    }


from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.services.embedding_service import get_query_embedding


def get_allowed_visibility(user_role: str) -> list[str]:
    visibility_by_role = {
        "admin": ["public", "student", "staff", "admin"],
        "student": ["public", "student"],
        "staff": ["public", "student", "staff"],
    }

    return visibility_by_role.get(
        (user_role or "").strip().lower(),
        ["public"],
    )


def search_knowledge(
    question: str,
    db: Session,
    user_role: str,
    limit: int = 5,
    min_similarity: float = 0.55,
) -> list[dict]:

    if not question or len(question.strip()) < 2:
        return []

    query_embedding = get_query_embedding(question.strip())
    allowed_visibility = get_allowed_visibility(user_role)

    distance = DocumentChunk.embedding.cosine_distance(query_embedding)

    statement = (
        select(
            DocumentChunk,
            Document,
            distance.label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.visibility.in_(allowed_visibility),
            Document.status == "completed",
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )

    rows = db.execute(statement).all()
    results = []

    for chunk, document, chunk_distance in rows:
        similarity = 1 - float(chunk_distance)

        if similarity < min_similarity:
            continue

        results.append({
            "document_id": document.id,
            "document_title": document.title,
            "chunk_id": chunk.id,
            "page_number": chunk.page_number,
            "content": chunk.content,
            "similarity": similarity,
        })

    return results

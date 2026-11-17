
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.services.embedding_service import get_model


MIN_SIMILARITY = float(
    os.getenv("RAG_MIN_SIMILARITY", "0.55")
)


def get_query_embedding(question: str) -> list[float]:
    question = question.strip()

    if not question:
        raise ValueError("Question cannot be empty")

    model = get_model()

    embedding = model.encode(
        [f"query: {question}"],
        normalize_embeddings=True,
        show_progress_bar=False
    )

    return embedding[0].tolist()


def get_allowed_visibility(user_role: str) -> list[str]:
    visibility_by_role = {
        "admin": ["public", "student", "staff", "admin"],
        "student": ["public", "student"],
        "staff": ["public", "staff"]
    }

    return visibility_by_role.get(user_role, ["public"])


def search_knowledge(
    question: str,
    db: Session,
    user_role: str,
    limit: int = 5,
    min_similarity: float = MIN_SIMILARITY
) -> list[dict]:

    if not question or not question.strip():
        return []

    allowed_visibility = get_allowed_visibility(user_role)

    query_embedding = get_query_embedding(question)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    ).label("distance")

    statement = (
        select(DocumentChunk, Document, distance)
        .join(
            Document,
            DocumentChunk.document_id == Document.id
        )
        .where(
            Document.visibility.in_(allowed_visibility),
            Document.status == "completed",
            DocumentChunk.embedding.is_not(None)
        )
        .order_by(distance)
        .limit(limit)
    )

    results = db.execute(statement).all()

    matches = []

    for chunk, document, distance_value in results:
        similarity = 1 - float(distance_value)

        if similarity < min_similarity:
            continue

        matches.append({
            "chunk_id": chunk.id,
            "document_id": document.id,
            "document_title": document.title,
            "document_language": document.language,
            "content": chunk.content,
            "page_number": chunk.page_number,
            "similarity": round(similarity, 4)
        })

    return matches

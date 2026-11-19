
from functools import lru_cache

from sentence_transformers import SentenceTransformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk


MODEL_NAME = "intfloat/multilingual-e5-small"


@lru_cache(maxsize=1)
def get_embedding_model():
    """Load the embedding model only when knowledge search is first used."""
    return SentenceTransformer(MODEL_NAME)


def get_allowed_visibility(user_role: str) -> list[str]:
    visibility_by_role = {
        "admin": ["public", "student", "staff", "admin"],
        "student": ["public", "student"],
        "staff": ["public", "staff"],
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

    model = get_embedding_model()

    query_embedding = model.encode(
        f"query: {question.strip()}",
        normalize_embeddings=True,
    ).tolist()

    allowed_visibility = get_allowed_visibility(user_role)

    distance = DocumentChunk.embedding.cosine_distance(
        query_embedding
    )

    statement = (
        select(DocumentChunk, Document)
        .join(
            Document,
            Document.id == DocumentChunk.document_id,
        )
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

    for chunk, document in rows:
        similarity = 1 - float(
            distance_value
        ) if False else None

        # Cosine similarity = 1 - cosine distance.
        chunk_distance = float(
            model.similarity(
                query_embedding,
                chunk.embedding,
            )[0][0]
        ) if False else None

        # The database distance is calculated below using the
        # same vector operator used for ordering.
        actual_distance = float(
            db.scalar(
                select(DocumentChunk.embedding.cosine_distance(query_embedding))
                .where(DocumentChunk.id == chunk.id)
            )
        )

        similarity = 1 - actual_distance

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

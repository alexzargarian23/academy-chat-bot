
import math
import os
from functools import lru_cache

from google import genai
from google.genai import types


MODEL_NAME = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768


@lru_cache(maxsize=1)
def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    return genai.Client(api_key=api_key)


def normalize_embedding(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))

    if norm == 0:
        raise ValueError("Gemini returned a zero-length embedding")

    return [value / norm for value in values]


def get_embeddings(
    texts: list[str],
    task_type: str,
) -> list[list[float]]:

    if not texts:
        return []

    client = get_gemini_client()

    response = client.models.embed_content(
        model=MODEL_NAME,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type,
            output_dimensionality=EMBEDDING_DIMENSION,
        ),
    )

    if not response.embeddings:
        raise RuntimeError("Gemini returned no embeddings")

    vectors = []

    for embedding in response.embeddings:
        values = embedding.values

        if len(values) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSION} dimensions, "
                f"received {len(values)}"
            )

        vectors.append(normalize_embedding(values))

    if len(vectors) != len(texts):
        raise RuntimeError(
            "Gemini returned an unexpected number of embeddings"
        )

    return vectors


def get_query_embedding(text: str) -> list[float]:
    return get_embeddings(
        [text],
        task_type="RETRIEVAL_QUERY",
    )[0]


def get_document_embeddings(texts: list[str]) -> list[list[float]]:
    return get_embeddings(
        texts,
        task_type="RETRIEVAL_DOCUMENT",
    )

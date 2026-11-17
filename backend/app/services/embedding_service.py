
from sentence_transformers import SentenceTransformer

MODEL_NAME = "intfloat/multilingual-e5-small"

_model = None


def get_model():
    global _model

    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)

    return _model


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = get_model()

    # E5 models expect document passages to use this prefix.
    passages = [f"passage: {text}" for text in texts]

    embeddings = model.encode(
        passages,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=False
    )

    return embeddings.tolist()

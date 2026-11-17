
import os
import logging
import time
from pathlib import Path
from typing import cast

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=ENV_FILE)

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL")
FALLBACK_MODEL_NAME = os.getenv("GEMINI_FALLBACK_MODEL")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY is not configured")

if not MODEL_NAME:
    raise ValueError("GEMINI_MODEL is not configured")

PRIMARY_MODEL_NAME: str = MODEL_NAME

client = genai.Client(
    api_key=API_KEY,
    http_options=types.HttpOptions(timeout=30_000),
)

RETRYABLE_CODES = {429, 500, 503, 504}
MAX_ATTEMPTS = 3


def _call_model(model_name: str, message: str) -> str:
    response = client.models.generate_content(
        model=model_name,
        contents=message,
        config={
            "temperature": 0.2,
        },
    )

    answer = response.text

    if not answer or not answer.strip():
        raise RuntimeError("Gemini returned an empty response")

    return answer.strip()


def generate_response(message: str) -> str:
    if not message or not message.strip():
        raise ValueError("Message cannot be empty")

    models = [PRIMARY_MODEL_NAME]
    fallback_model_name = FALLBACK_MODEL_NAME
    if (
        isinstance(fallback_model_name, str)
        and fallback_model_name != PRIMARY_MODEL_NAME
    ):
        models.append(cast(str, fallback_model_name))

    last_error = None

    for model_name in models:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return _call_model(model_name, message)
            except errors.APIError as error:
                last_error = error
                logger.warning(
                    "Gemini request failed for model %s (attempt %s/%s): %s",
                    model_name,
                    attempt,
                    MAX_ATTEMPTS,
                    error,
                )

                if error.code not in RETRYABLE_CODES:
                    break

                if attempt < MAX_ATTEMPTS:
                    time.sleep(2 ** (attempt - 1))
            except RuntimeError:
                raise

    raise RuntimeError("Gemini is unavailable right now") from last_error

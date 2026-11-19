
import os
import math
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in backend/.env")

client = genai.Client(api_key=api_key)

samples = {
    "English": "Artificial intelligence helps students learn programming.",
    "Armenian": "Արհեստական բանականությունն օգնում է ուսանողներին սովորել։",
    "Russian": "Искусственный интеллект помогает студентам изучать программирование.",
}

for language, text in samples.items():
    result = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
        ),
    )

    values = result.embeddings[0].values
    norm = math.sqrt(sum(value * value for value in values))

    print(f"{language}: dimensions={len(values)}, norm={norm:.4f}")

print("Gemini embedding test completed.")

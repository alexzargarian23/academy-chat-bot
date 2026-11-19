
from sqlalchemy.orm import Session

from app.services.assistant_service import generate_text_response


def answer_question(
    question: str,
    db: Session,
    user_role: str,
    conversation_history: list[dict] | None = None
) -> dict:

    history = conversation_history or []

    history_text = "\n".join(
        f"{message['sender'].capitalize()}: {message['content']}"
        for message in history[-10:]
        if message.get("sender") in ["user", "assistant"]
    )

    if not history_text:
        history_text = "No previous conversation."

    prompt = f"""
You are the official multilingual AI assistant of an Academy.

CONVERSATION HISTORY:
{history_text}

CURRENT QUESTION:
{question}

INSTRUCTIONS:
1. Respond in the same language as the user's question:
   Armenian, English, or Russian.
2. Be helpful, clear, and concise.
3. Never invent Academy-specific information,
   including prices, schedules, policies, or admission requirements.
4. If you don't know an Academy-specific fact,
   recommend contacting Academy staff.
5. Use conversation history to understand context.
6. Never claim to have accessed personal student records.

Write your answer now.
"""

    answer = generate_text_response(prompt)

    return {
        "answer": answer,
        "sources": [],
        "handoff_required": False,
        "handoff_reason": None
    }

np# Academy Concierge frontend

A React + Vite website with student registration/login, a chat interface, conversation history, new chats, and responsive layout.

## Run it

1. Start the FastAPI backend from `backend/`:
   `uvicorn app.main:app --reload`
2. In this folder run:
   `cp .env.example .env`
   `npm install`
   `npm run dev`
3. Open the Vite URL (usually http://localhost:5173).

Set `VITE_API_URL` in `.env` if the backend is hosted elsewhere.

## Required backend CORS change

The browser app runs on port 5173 and FastAPI on port 8000. Add CORS middleware to `app/main.py` after creating the FastAPI app:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Keep your existing FastAPI app and router registration; do not create a second app instance.

## Backend endpoints used

- `POST /users/login`
- `POST /users/register`
- `GET /users/me`
- `GET /conversations/`
- `POST /conversations/`
- `DELETE /conversations/{id}`
- `GET /conversations/{id}/messages`
- `POST /ai/chat`

Conversation titles are generated from the first user question and displayed with the creation date. The UI allows users to permanently delete conversations after confirmation.

-- Persist RAG source metadata on assistant messages for clickable citations.
ALTER TABLE messages
    ADD COLUMN IF NOT EXISTS sources JSONB NULL;

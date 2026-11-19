-- Add persistent titles for the website conversation history.
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS title VARCHAR(120) NULL;

WITH first_user_message AS (
    SELECT DISTINCT ON (conversation_id)
        conversation_id,
        regexp_replace(trim(content), '\s+', ' ', 'g') AS normalized_title
    FROM messages
    WHERE sender = 'user'
    ORDER BY conversation_id, created_at ASC, id ASC
)
UPDATE conversations AS conversations
SET title = CASE
    WHEN length(first_user_message.normalized_title) > 120
        THEN left(first_user_message.normalized_title, 117) || '...'
    ELSE first_user_message.normalized_title
END
FROM first_user_message
WHERE conversations.id = first_user_message.conversation_id
  AND conversations.title IS NULL;

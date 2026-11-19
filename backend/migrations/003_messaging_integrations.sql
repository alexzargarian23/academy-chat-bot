-- Telegram and Slack identity mapping and webhook idempotency.
CREATE TABLE IF NOT EXISTS channel_identities (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(20) NOT NULL,
    external_user_id VARCHAR(255) NOT NULL,
    display_name VARCHAR(150) NOT NULL DEFAULT 'Guest',
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_channel_identity_provider_user UNIQUE (provider, external_user_id)
);
CREATE INDEX IF NOT EXISTS ix_channel_identities_provider ON channel_identities(provider);
CREATE INDEX IF NOT EXISTS ix_channel_identities_user_id ON channel_identities(user_id);
CREATE INDEX IF NOT EXISTS ix_channel_identities_conversation_id ON channel_identities(conversation_id);
ALTER TABLE channel_identities
    ADD COLUMN IF NOT EXISTS authenticated BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS authenticated_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS auth_stage VARCHAR(20) NULL,
    ADD COLUMN IF NOT EXISTS pending_email VARCHAR(255) NULL,
    ADD COLUMN IF NOT EXISTS failed_auth_attempts INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS channel_events (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(20) NOT NULL,
    event_id VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'received',
    response_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_channel_event_provider_event UNIQUE (provider, event_id)
);
CREATE INDEX IF NOT EXISTS ix_channel_events_provider ON channel_events(provider);

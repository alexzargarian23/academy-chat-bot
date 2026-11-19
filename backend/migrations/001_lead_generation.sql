-- Apply once to an existing PostgreSQL database before starting the updated backend.
-- For a completely new database, SQLAlchemy create_all creates these columns itself.

ALTER TABLE applicant_leads
    ADD COLUMN IF NOT EXISTS user_id INTEGER NULL REFERENCES users(id),
    ADD COLUMN IF NOT EXISTS source VARCHAR(40) NOT NULL DEFAULT 'website_registration',
    ADD COLUMN IF NOT EXISTS contact_consent BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS qualification_notes TEXT NULL;

CREATE INDEX IF NOT EXISTS ix_applicant_leads_user_id ON applicant_leads(user_id);

-- Keep one lead per account. Existing duplicate user_id values must be resolved first.
CREATE UNIQUE INDEX IF NOT EXISTS uq_applicant_leads_user_id
    ON applicant_leads(user_id)
    WHERE user_id IS NOT NULL;

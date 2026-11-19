-- PostgreSQL migration. Back up the database before applying.
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS applicant_lead_id INTEGER NULL REFERENCES applicant_leads(id);
CREATE INDEX IF NOT EXISTS ix_conversations_applicant_lead_id ON conversations(applicant_lead_id);
ALTER TABLE appointments ALTER COLUMN student_profile_id DROP NOT NULL;
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS applicant_lead_id INTEGER NULL REFERENCES applicant_leads(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_appointments_applicant_lead_id ON appointments(applicant_lead_id);
CREATE TABLE IF NOT EXISTS academy_emails (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(500) NOT NULL UNIQUE,
    sender VARCHAR(500) NOT NULL,
    recipient VARCHAR(500) NOT NULL,
    subject VARCHAR(1000) NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reply_draft TEXT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'received',
    approved_by INTEGER NULL REFERENCES users(id),
    sent_at TIMESTAMPTZ NULL,
    staff_approved BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_academy_emails_message_id ON academy_emails(message_id);
CREATE INDEX IF NOT EXISTS ix_academy_emails_status ON academy_emails(status);

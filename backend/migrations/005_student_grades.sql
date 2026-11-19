-- Private student grades for staff review and authenticated student access.
CREATE TABLE IF NOT EXISTS student_grades (
    id SERIAL PRIMARY KEY,
    student_profile_id INTEGER NOT NULL REFERENCES student_profiles(id) ON DELETE CASCADE,
    schedule_id INTEGER NOT NULL REFERENCES class_schedules(id),
    assessment_name VARCHAR(200) NOT NULL,
    score NUMERIC(6, 2) NOT NULL,
    max_score NUMERIC(6, 2) NOT NULL,
    letter_grade VARCHAR(10),
    academic_year VARCHAR(30) NOT NULL,
    feedback TEXT,
    graded_at DATE NOT NULL DEFAULT CURRENT_DATE,
    graded_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_student_grades_student_profile_id ON student_grades(student_profile_id);
CREATE INDEX IF NOT EXISTS ix_student_grades_schedule_id ON student_grades(schedule_id);

from alembic import op

revision = "0001_legacy"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE archy.accounts_user (password varchar(128) NOT NULL, "
        "last_login timestamp with time zone, is_superuser boolean NOT NULL, id uuid"
        " NOT NULL, email varchar(254) NOT NULL, display_name varchar(100) NOT NULL,"
        " is_active boolean NOT NULL, is_staff boolean NOT NULL, created_at "
        "timestamp with time zone NOT NULL, updated_at timestamp with time zone NOT "
        "NULL, email_confirmed_at timestamp with time zone, CONSTRAINT "
        "accounts_user_email_key UNIQUE (email), CONSTRAINT accounts_user_pkey "
        "PRIMARY KEY (id))"
    )
    op.execute(
        "CREATE INDEX accounts_user_email_b2644a56_like ON archy.accounts_user USING"
        " btree (email varchar_pattern_ops)"
    )
    op.execute(
        "CREATE UNIQUE INDEX user_email_case_unique ON archy.accounts_user USING "
        "btree (lower((email)::text))"
    )
    op.execute(
        "CREATE TABLE archy.accounts_signupattempt (id uuid NOT NULL, password_hash "
        "varchar(128) NOT NULL, display_name varchar(100) NOT NULL, created_at "
        "timestamp with time zone NOT NULL, user_id uuid NOT NULL, CONSTRAINT "
        "accounts_signupattempt_pkey PRIMARY KEY (id), CONSTRAINT "
        "accounts_signupattempt_user_id_58cd6f0b_fk_accounts_user_id FOREIGN KEY "
        "(user_id) REFERENCES accounts_user(id) DEFERRABLE INITIALLY DEFERRED)"
    )
    op.execute(
        "CREATE INDEX accounts_signupattempt_user_id_58cd6f0b ON "
        "archy.accounts_signupattempt USING btree (user_id)"
    )
    op.execute(
        "CREATE TABLE archy.courses_course (id uuid NOT NULL, title varchar(100) NOT"
        " NULL, archived_at timestamp with time zone, created_at timestamp with time"
        " zone NOT NULL, updated_at timestamp with time zone NOT NULL, owner_id uuid"
        " NOT NULL, CONSTRAINT course_title_valid CHECK (((length(TRIM(BOTH FROM "
        "title)) > 0) AND (length((title)::text) <= 100) AND ((title)::text = "
        "TRIM(BOTH FROM title)))), CONSTRAINT "
        "courses_course_owner_id_97a468c6_fk_accounts_user_id FOREIGN KEY (owner_id)"
        " REFERENCES accounts_user(id) DEFERRABLE INITIALLY DEFERRED, CONSTRAINT "
        "courses_course_pkey PRIMARY KEY (id))"
    )
    op.execute(
        "CREATE INDEX courses_course_owner_id_97a468c6 ON archy.courses_course USING"
        " btree (owner_id)"
    )
    op.execute(
        "CREATE TABLE archy.recordings_upload (id uuid NOT NULL, title varchar(100) "
        "NOT NULL, file_name varchar(255) NOT NULL, size_bytes bigint NOT NULL, "
        "uploaded_bytes bigint NOT NULL, sha256 varchar(64) NOT NULL, status "
        "varchar(12) NOT NULL, error_code varchar(32) NOT NULL, created_at timestamp"
        " with time zone NOT NULL, updated_at timestamp with time zone NOT NULL, "
        "course_id uuid NOT NULL, CONSTRAINT "
        "recordings_upload_course_id_13a40453_fk_courses_course_id FOREIGN KEY "
        "(course_id) REFERENCES courses_course(id) DEFERRABLE INITIALLY DEFERRED, "
        "CONSTRAINT recordings_upload_pkey PRIMARY KEY (id), CONSTRAINT "
        "recordings_upload_size_bytes_check CHECK ((size_bytes >= 0)), CONSTRAINT "
        "recordings_upload_uploaded_bytes_check CHECK ((uploaded_bytes >= 0)), "
        "CONSTRAINT upload_offset_valid CHECK ((uploaded_bytes <= size_bytes)), "
        "CONSTRAINT upload_size_valid CHECK (((size_bytes > 0) AND (size_bytes <= "
        "'9007199254740991'::bigint))), CONSTRAINT upload_status_valid CHECK (status"
        " IN ('UPLOADING','ACCEPTED','FAILED','CANCELLED')), CONSTRAINT "
        "upload_title_valid CHECK (((length(TRIM(BOTH FROM title)) > 0) AND "
        "(length((title)::text) <= 100) AND ((title)::text = TRIM(BOTH FROM "
        "title)))))"
    )
    op.execute(
        "CREATE INDEX recordings__course__619b85_idx ON archy.recordings_upload "
        "USING btree (course_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX recordings_upload_course_id_13a40453 ON "
        "archy.recordings_upload USING btree (course_id)"
    )
    op.execute(
        "CREATE TABLE archy.recordings_recording (id uuid NOT NULL, title "
        "varchar(100) NOT NULL, size_bytes bigint NOT NULL, sha256 varchar(64) NOT "
        "NULL, content_type varchar(32) NOT NULL, duration_seconds double precision,"
        " created_at timestamp with time zone NOT NULL, course_id uuid NOT NULL, "
        "upload_id uuid NOT NULL, CONSTRAINT "
        "recordings_recording_course_id_e8867e2e_fk_courses_course_id FOREIGN KEY "
        "(course_id) REFERENCES courses_course(id) DEFERRABLE INITIALLY DEFERRED, "
        "CONSTRAINT recordings_recording_pkey PRIMARY KEY (id), CONSTRAINT "
        "recordings_recording_size_bytes_check CHECK ((size_bytes >= 0)), CONSTRAINT"
        " recordings_recording_upload_id_6cab6225_fk_recordings_upload_id FOREIGN "
        "KEY (upload_id) REFERENCES recordings_upload(id) DEFERRABLE INITIALLY "
        "DEFERRED, CONSTRAINT recordings_recording_upload_id_key UNIQUE (upload_id))"
    )
    op.execute(
        "CREATE INDEX recordings__course__41d681_idx ON archy.recordings_recording "
        "USING btree (course_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX recordings_recording_course_id_e8867e2e ON "
        "archy.recordings_recording USING btree (course_id)"
    )


def downgrade():
    raise RuntimeError("Baseline downgrade is not supported; restore a reviewed backup.")

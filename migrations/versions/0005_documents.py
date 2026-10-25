from alembic import op

revision = "0005_documents"
down_revision = "0004_processing"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "\nCREATE TABLE archy.documents_document (\n\tid UUID NOT NULL, \n\towner_id UUID NOT NULL, \n\ttitle VARCHAR(100) NOT NULL, \n\tcourse_id UUID, \n\trecording_id UUID, \n\tfile_name VARCHAR(255), \n\tpdf_size_bytes BIGINT, \n\tpage_count INTEGER, \n\ttext TEXT, \n\tarchived_at TIMESTAMP WITH TIME ZONE, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tCONSTRAINT pk_documents_document PRIMARY KEY (id), \n\tCONSTRAINT ck_documents_document_title_valid CHECK (length(trim(title)) > 0 AND length(title) <= 100 AND title = trim(title)), \n\tCONSTRAINT ck_documents_document_pdf_metadata_valid CHECK ((file_name IS NULL) = (pdf_size_bytes IS NULL)), \n\tCONSTRAINT ck_documents_document_pdf_size_valid CHECK (pdf_size_bytes IS NULL OR pdf_size_bytes BETWEEN 1 AND 20971520), \n\tCONSTRAINT ck_documents_document_page_count_valid CHECK (page_count IS NULL OR page_count BETWEEN 1 AND 200), \n\tCONSTRAINT ck_documents_document_text_size_valid CHECK (text IS NULL OR length(text) <= 500000), \n\tCONSTRAINT fk_documents_document_owner_id_accounts_user FOREIGN KEY(owner_id) REFERENCES archy.accounts_user (id), \n\tCONSTRAINT fk_documents_document_course_id_courses_course FOREIGN KEY(course_id) REFERENCES archy.courses_course (id), \n\tCONSTRAINT fk_documents_document_recording_id_recordings_recording FOREIGN KEY(recording_id) REFERENCES archy.recordings_recording (id)\n)\n\n"
    )
    op.execute(
        "CREATE INDEX ix_documents_owner_created ON archy.documents_document (owner_id, created_at, id)"
    )
    op.execute(
        "INSERT INTO archy.documents_document (id, owner_id, title, course_id, recording_id, created_at, updated_at) SELECT r.id, c.owner_id, r.title, r.course_id, r.id, r.created_at, r.created_at FROM archy.recordings_recording r JOIN archy.courses_course c ON c.id = r.course_id ON CONFLICT (id) DO NOTHING"
    )


def downgrade():
    op.drop_table("documents_document", schema="archy")

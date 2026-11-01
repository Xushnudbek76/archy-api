import sqlalchemy as sa
from alembic import op

revision = "0017_document_pins"
down_revision = "0016_academic_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents_document",
        sa.Column("is_pinned", sa.Boolean, nullable=False, server_default=sa.false()),
        schema="archy",
    )
    op.create_index(
        "ix_documents_owner_recording",
        "documents_document",
        ["owner_id", "recording_id"],
        schema="archy",
    )


def downgrade():
    op.drop_index("ix_documents_owner_recording", table_name="documents_document", schema="archy")
    op.drop_column("documents_document", "is_pinned", schema="archy")

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_study_notes"
down_revision = "0006_document_pages"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_note",
        sa.Column(
            "document_id", sa.Uuid, sa.ForeignKey("archy.documents_document.id"), primary_key=True
        ),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('en','ko')", name="ck_study_note_language_valid"),
        schema="archy",
    )


def downgrade():
    op.drop_table("study_note", schema="archy")

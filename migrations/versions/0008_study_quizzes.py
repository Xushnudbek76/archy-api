import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0008_study_quizzes"
down_revision = "0007_study_notes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_quiz",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "document_id", sa.Uuid, sa.ForeignKey("archy.documents_document.id"), nullable=False
        ),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("questions", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IN ('en','ko')", name="ck_study_quiz_language_valid"),
        schema="archy",
    )


def downgrade():
    op.drop_table("study_quiz", schema="archy")

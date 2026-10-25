import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_tutor_conversations"
down_revision = "0010_quiz_retries"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tutor_conversation",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), nullable=False),
        sa.Column(
            "document_id", sa.Uuid, sa.ForeignKey("archy.documents_document.id"), nullable=False
        ),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="archy",
    )
    op.create_index(
        "ix_tutor_conversation_document",
        "tutor_conversation",
        ["document_id", "created_at"],
        schema="archy",
    )
    op.create_table(
        "tutor_message",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "conversation_id", sa.Uuid, sa.ForeignKey("archy.tutor_conversation.id"), nullable=False
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("sources", JSONB, nullable=False),
        sa.Column("provider", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_tutor_message_role_valid"),
        schema="archy",
    )
    op.create_index(
        "ix_tutor_message_conversation",
        "tutor_message",
        ["conversation_id", "created_at"],
        schema="archy",
    )


def downgrade():
    op.drop_table("tutor_message", schema="archy")
    op.drop_table("tutor_conversation", schema="archy")

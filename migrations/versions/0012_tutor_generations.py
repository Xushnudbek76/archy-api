import sqlalchemy as sa
from alembic import op

revision = "0012_tutor_generations"
down_revision = "0011_tutor_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tutor_generation",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column(
            "conversation_id", sa.Uuid, sa.ForeignKey("archy.tutor_conversation.id"), nullable=False
        ),
        sa.Column("request_id", sa.Uuid, nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("lease_token", sa.Uuid, nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assistant_id", sa.Uuid, sa.ForeignKey("archy.tutor_message.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("conversation_id", "request_id"),
        sa.CheckConstraint(
            "status IN ('active','completed','failed')", name="ck_tutor_generation_status_valid"
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL) = (lease_expires_at IS NULL)",
            name="ck_tutor_generation_lease_valid",
        ),
        schema="archy",
    )
    op.create_index(
        "ix_tutor_generation_lease",
        "tutor_generation",
        ["status", "lease_expires_at"],
        schema="archy",
    )


def downgrade():
    op.drop_table("tutor_generation", schema="archy")

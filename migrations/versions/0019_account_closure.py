import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019_account_closure"
down_revision = "0018_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "preferences_media_purge",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), nullable=False),
        sa.Column("media", JSONB, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 8", name=op.f("ck_preferences_media_purge_attempts_valid")
        ),
        schema="archy",
    )


def downgrade():
    op.drop_table("preferences_media_purge", schema="archy")

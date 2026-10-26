import sqlalchemy as sa
from alembic import op

revision = "0013_tutor_usage"
down_revision = "0012_tutor_generations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tutor_usage",
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), primary_key=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= 10", name="ck_tutor_usage_attempts_valid"
        ),
        schema="archy",
    )


def downgrade():
    op.drop_table("tutor_usage", schema="archy")

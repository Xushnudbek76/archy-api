import sqlalchemy as sa
from alembic import op

revision = "0010_quiz_retries"
down_revision = "0009_study_attempts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_quiz_retry",
        sa.Column("attempt_id", sa.Uuid, sa.ForeignKey("archy.study_attempt.id"), primary_key=True),
        sa.Column(
            "quiz_id", sa.Uuid, sa.ForeignKey("archy.study_quiz.id"), nullable=False, unique=True
        ),
        schema="archy",
    )


def downgrade():
    op.drop_table("study_quiz_retry", schema="archy")

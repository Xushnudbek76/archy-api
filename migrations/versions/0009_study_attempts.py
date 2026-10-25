import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009_study_attempts"
down_revision = "0008_study_quizzes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_attempt",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("quiz_id", sa.Uuid, sa.ForeignKey("archy.study_quiz.id"), nullable=False),
        sa.Column("answer_digest", sa.String(64), nullable=False),
        sa.Column("score", sa.Integer, nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("results", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("quiz_id", "answer_digest"),
        sa.CheckConstraint(
            "score >= 0 AND score <= total AND total BETWEEN 1 AND 15",
            name="ck_study_attempt_score_valid",
        ),
        schema="archy",
    )


def downgrade():
    op.drop_table("study_attempt", schema="archy")

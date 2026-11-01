import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016_academic_imports"
down_revision = "0015_course_schedules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "academics_import",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("archy.accounts_user.id"), nullable=False),
        sa.Column("timetable_id", sa.Uuid, nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("course_ids", JSONB, nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "timetable_id"],
            ["archy.academics_timetable.owner_id", "archy.academics_timetable.id"],
        ),
        schema="archy",
    )
    op.create_index(
        "ix_academics_import_owner_id", "academics_import", ["owner_id"], schema="archy"
    )


def downgrade():
    op.drop_table("academics_import", schema="archy")
